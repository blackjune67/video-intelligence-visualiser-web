from google.cloud import videointelligence
from google.api_core import exceptions
from google.cloud import storage
import time
import datetime
import concurrent.futures
import os
import json
import re
import requests

# 전역 변수로 버킷 정보 설정
GCS_BUCKET = "highbuff_developer_seoul"
INPUT_PREFIX = "visualize-input/" # RTSP (실시간) 영상 저장 폴더의 경로
TEMP_OUTPUT_PREFIX = "temp-output-json-files/" # 구글 비디오 영상 분석 업로드된 JSON파일의 경로
AWS_OUTPUT_PREFIX = "visualize-aws-output-files/" # AWS에 업로드된 JSON 파일 (explicit_annotation)의 경로
FINAL_OUTPUT_PREFIX = "visualize-final-output-files/" # 최종 합쳐진 JSON 파일의 경로
VIEW_FINAL_OUTPUT_PREFIX = "visualize-view-final-output-files/" # 웹에서 보여질 파일의 경로



# 재시도 로직을 포함한 파일 업로드 함수
def upload_blob_with_retry(blob, data, retries=5, delay=1):
    for attempt in range(retries):
        try:
            blob.upload_from_string(data)
            print(f"업로드 성공: {blob.name}")
            return
        except exceptions.TooManyRequests as e:
            if attempt < retries - 1:
                wait_time = delay * (2 ** attempt)
                print(f"429 오류: {wait_time}초 후에 재시도합니다.")
                time.sleep(wait_time)
            else:
                print("최대 재시도 횟수 초과. 업로드 실패.")
                raise

# 영상 변환
def process_video(video_name, gcs_client, timeout=1800):
    # {datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json

    gcs_uri = f"gs://{GCS_BUCKET}/{INPUT_PREFIX}{video_name}"
    output_filename = f"{os.path.splitext(video_name)[0]}-{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    temp_output_uri = f"gs://{GCS_BUCKET}/{TEMP_OUTPUT_PREFIX}{output_filename}"

    try:
        print("\n")
        print("\n처리를 시작합니다. 비디오 크기에 따라 시간이 오래 걸릴 수 있습니다.")
        print("\n")
        
        video_client = videointelligence.VideoIntelligenceServiceClient.from_service_account_file(
            "/Users/highbuff/Downloads/gold-braid-428103-s3-1806cc6a21a0.json")

        features = [
            videointelligence.Feature.FACE_DETECTION,
            videointelligence.Feature.OBJECT_TRACKING,
            videointelligence.Feature.EXPLICIT_CONTENT_DETECTION
        ]

        transcript_config = videointelligence.SpeechTranscriptionConfig(
            language_code="en-US", enable_automatic_punctuation=True
        )

        person_config = videointelligence.PersonDetectionConfig(
            include_bounding_boxes=True,
            include_attributes=False,
            include_pose_landmarks=True,
        )

        face_config = videointelligence.FaceDetectionConfig(
            include_bounding_boxes=True, include_attributes=True
        )

        video_context = videointelligence.VideoContext(
            speech_transcription_config=transcript_config,
            person_detection_config=person_config,
            face_detection_config=face_config)

        operation = video_client.annotate_video(
            request={"features": features,
                     "input_uri": gcs_uri,
                     "output_uri": temp_output_uri,
                     "video_context": video_context}
        )

        print(f"\n'{video_name}' 비디오를 처리하고 있습니다...")
        result = operation.result(timeout=timeout)
        print("\n처리가 완료되었습니다.")
        print(f"결과가 다음 위치에 저장되었습니다: {temp_output_uri}")

        merge_json_files(gcs_client, output_filename)
        
        return result

    except exceptions.NotFound as e:
        print(f"오류: '{video_name}' 파일을 '{GCS_BUCKET}/{INPUT_PREFIX}' 폴더에서 찾을 수 없습니다.")
        print("다음 사항을 확인해 주세요:")
        print("1. 파일 이름이 정확한지 확인하세요.")
        print(f"2. 해당 파일이 실제로 '{GCS_BUCKET}/{INPUT_PREFIX}' 폴더에 존재하는지 확인하세요.")
        print("3. 접근 권한이 올바르게 설정되어 있는지 확인하세요.")
    except concurrent.futures.TimeoutError:
        print(f"처리 시간이 {timeout/60:.0f}분을 초과했습니다.")
        print("더 긴 처리 시간이 필요하다면, 관리자에게 문의해 주세요.")
    except exceptions.Forbidden as e:
        print("오류: 이 리소스에 접근할 권한이 없습니다.")
        print("접근 권한 설정을 확인해 주세요. 필요하다면 관리자에게 문의하세요.")
    except exceptions.GoogleAPICallError as e:
        print("API 호출 중 오류가 발생했습니다.")
        print(f"네트워크 연결을 확인하고, 문제가 지속되면 관리자에게 문의해 주세요. {e}")
    except Exception as e:
        print("예상치 못한 오류가 발생했습니다:")
        print(f"오류 메시지: {e}")
        print("이 오류가 계속되면 관리자에게 문의해 주세요.")


# AWS, GCP의 파일명을 비교해서 가져온다.
def get_files_with_timestamps(gcs_client, prefix):
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs(prefix=prefix))
    files_with_timestamps = {}
    
    for blob in blobs:
        match = re.search(r'(\d{8}_\d{6})', blob.name)
        if match:
            timestamp = match.group(1)
            files_with_timestamps[timestamp] = blob.name
    
    return files_with_timestamps


# AWS, GCP의 JSON 병합
# def merge_json_files(gcs_client):
    aws_files = get_files_with_timestamps(gcs_client, AWS_OUTPUT_PREFIX)
    temp_files = get_files_with_timestamps(gcs_client, TEMP_OUTPUT_PREFIX)
    
    matching_timestamps = set(aws_files.keys()) & set(temp_files.keys())
    # matching_timestamps = set(aws_files.keys()) | set(temp_files.keys())
    
    for timestamp in matching_timestamps:
        aws_file = aws_files[timestamp]
        temp_file = temp_files[timestamp]
        # aws_file = aws_files.get(timestamp)
        # temp_file = temp_files.get(timestamp)
        
        print(f"매칭되는 파일 발견: \nAWS: {aws_file}\nTemp: {temp_file}")
        
        bucket = gcs_client.bucket(GCS_BUCKET)
        
        if aws_file:
            # AWS JSON 파일 읽기
            aws_blob = bucket.blob(aws_file)
            aws_data = json.loads(aws_blob.download_as_text())
        else:
            aws_data = {}
        
        # Temp JSON 파일 읽기
        temp_blob = bucket.blob(temp_file)
        temp_data = json.loads(temp_blob.download_as_text())
        
        # JSON 병합
        if 'annotation_results' in temp_data and len(temp_data['annotation_results']) > 0:
            # GCP 데이터의 첫 번째 annotation_result에 AWS 데이터 추가
            temp_data['annotation_results'][0]['explicit_annotation'] = aws_data.get('explicit_annotation', {})
        else:
            # annotation_results가 없거나 비어있는 경우 새로 생성
            temp_data['annotation_results'] = [{
                'face_detection_annotations': [],
                'explicit_annotation': aws_data.get('explicit_annotation', {}),
                'object_annotations': []
            }]
        
        # 병합된 JSON 저장
        merged_filename = f"merged_{timestamp}.json"
        merged_blob = bucket.blob(f"{FINAL_OUTPUT_PREFIX}{merged_filename}")
        merged_blob.upload_from_string(json.dumps(temp_data))
        

        # 병합된 JSON을 final_output.json으로 저장
        final_finlename= "final_output.json"
        final_output_blob = bucket.blob(f"{VIEW_FINAL_OUTPUT_PREFIX}{final_finlename}")
        final_output_blob.upload_from_string(json.dumps(temp_data))
        
        print(f"병합된 JSON 파일 저장 완료: gs://{GCS_BUCKET}/{FINAL_OUTPUT_PREFIX}{merged_filename}")
        print(f"복사된 최종 JSON 파일 저장 완료: gs://{GCS_BUCKET}/{VIEW_FINAL_OUTPUT_PREFIX}{final_finlename}")

def merge_json_files(gcs_client, temp_filename):
    aws_files = get_files_with_timestamps(gcs_client, AWS_OUTPUT_PREFIX)
    
    match = re.search(r'(\d{8}_\d{6})', temp_filename)
    if not match:
        print(f"타임스탬프를 찾을 수 없습니다: {temp_filename}")
        return
    
    timestamp = match.group(1)
    aws_file = aws_files.get(timestamp)
    if not aws_file:
        print(f"해당 타임스탬프와 매칭되는 AWS 파일이 없습니다: {timestamp}")
        return
    
    print(f"매칭되는 파일 발견: \nAWS: {aws_file}\nTemp: {temp_filename}")
    
    bucket = gcs_client.bucket(GCS_BUCKET)
    
    merged_filename = f"merged_{timestamp}.json"
    merged_blob = bucket.blob(f"{FINAL_OUTPUT_PREFIX}{merged_filename}")
    if merged_blob.exists():
        print(f"이미 병합된 파일이 존재합니다: {merged_filename}")
        return
    
    # AWS JSON 파일 읽기
    aws_blob = bucket.blob(aws_file)
    aws_data = json.loads(aws_blob.download_as_text())
    
    # Temp JSON 파일 읽기
    temp_blob = bucket.blob(f"{TEMP_OUTPUT_PREFIX}{temp_filename}")
    temp_data = json.loads(temp_blob.download_as_text())
    
    # JSON 병합
    if 'annotation_results' in temp_data and len(temp_data['annotation_results']) > 0:
        # GCP 데이터의 첫 번째 annotation_result에 AWS 데이터 추가
        temp_data['annotation_results'][0]['explicit_annotation'] = aws_data.get('explicit_annotation', {})
    else:
        # annotation_results가 없거나 비어있는 경우 새로 생성
        temp_data['annotation_results'] = [{
            'face_detection_annotations': [],
            'explicit_annotation': aws_data.get('explicit_annotation', {}),
            'object_annotations': []
        }]
    
    # 병합된 JSON 저장
    # merged_filename = f"merged_{timestamp}.json"
    # merged_blob = bucket.blob(f"{FINAL_OUTPUT_PREFIX}{merged_filename}")
    merged_blob.upload_from_string(json.dumps(temp_data))
    merged_blob.cache_control = "no-cache"
    merged_blob.patch()

    final_filename = "final_output.json"
    final_output_blob = bucket.blob(f"{VIEW_FINAL_OUTPUT_PREFIX}{final_filename}")

    # # final_output.json이 이미 존재하는지 확인
    # if final_output_blob.exists():
    #     print(f"{final_filename}이 이미 존재합니다. 삭제 후 새로 업로드합니다.")
    #     final_output_blob.delete()
    
    # # 새로운 final_output.json 업로드
    final_output_blob.upload_from_string(json.dumps(temp_data))
    final_output_blob.cache_control = "no-cache"
    final_output_blob.patch()

    # 콜백 함수
    notify_merge_complete()

    print(f"병합된 JSON 파일 저장 완료: gs://{GCS_BUCKET}/{FINAL_OUTPUT_PREFIX}{merged_filename}")
    print(f"복사된 최종 JSON 파일 저장 완료: gs://{GCS_BUCKET}/{VIEW_FINAL_OUTPUT_PREFIX}{final_filename}")

# 최신 영상 가져오기
def get_latest_video(gcs_client):
    bucket = gcs_client.bucket(GCS_BUCKET)
    blobs = list(bucket.list_blobs(prefix=INPUT_PREFIX))
    video_files = [blob for blob in blobs if blob.name.lower().endswith('.mp4')]
    
    if not video_files:
        return None
    
    latest_file = max(video_files, key=lambda x: x.time_created)
    return latest_file.name.split('/')[-1]

# 새로운 영상을 5초 마다 감지
def process_new_videos(gcs_client):
    processed_videos = set()
    
    while True:
        latest_video = get_latest_video(gcs_client)
        print(f'==> 최신 영상 : {latest_video}')
        api_url = "http://localhost:5555/api/v1/moderation/create"

        if latest_video and latest_video not in processed_videos:
            print(f"새로운 영상 파일 감지: {latest_video}")

            # API 호출
            api_data = {
                "bucketName": GCS_BUCKET,
                "objectKey": latest_video
            }
            try:
                response = requests.post(api_url, json=api_data)
                response.raise_for_status()
                print(f"API 호출 성공: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"API 호출 실패: {e}")


            output_filename = process_video(latest_video, gcs_client)
            if output_filename:
                # merge_json_files(gcs_client)
                processed_videos.add(latest_video)
        
        time.sleep(5)  # 5초마다 새 비디오 확인

def notify_merge_complete():
    try:
        response = requests.get('http://localhost:8080/merge-complete')
        if response.status_code == 200:
            print("Merge completion notified successfully.")
        else:
            print("Failed to notify merge completion.")
    except Exception as e:
        print(f"Error notifying merge completion: {e}")

if __name__ == "__main__":
    gcs_client = storage.Client.from_service_account_json("/Users/highbuff/Downloads/gold-braid-428103-s3-1806cc6a21a0.json")

    try:
        process_new_videos(gcs_client)
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")