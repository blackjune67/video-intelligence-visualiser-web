import os
import time
import json
import concurrent.futures
from google.cloud import videointelligence
from google.api_core import exceptions
from google.cloud import storage
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 전역 변수로 버킷 정보 설정
GCS_BUCKET = "gs://highbuff_developer_seoul/"
INPUT_PREFIX = "visualize-input/" # RTSP (실시간) 영상 저장 폴더의 경로
OUTPUT_PREFIX = "stream-video/" # 테스트 폴더의 경로
AWS_OUTPUT_PREFIX = "visualize-aws-output/" # AWS에 업로드된 JSON파일 (explicit_annotation)의 경로
FINAL_OUTPUT_PREFIX = "visualize-final-output-files/" # 최종 JSON파일의 경로

def process_video(video_name, gcs_client, timeout=1800):
    print("==> process_video")
    gcs_uri = GCS_BUCKET + INPUT_PREFIX + video_name
    output_filename = f"output-{os.path.splitext(video_name)[0]}.json"
    output_uri = GCS_BUCKET + AWS_OUTPUT_PREFIX + output_filename

    try:
        print("\n영상 분석 처리를 시작합니다. 비디오 크기에 따라 시간이 오래 걸릴 수 있습니다.")

        video_client = videointelligence.VideoIntelligenceServiceClient.from_service_account_file(
            "/Users/highbuff/Downloads/gold-braid-428103-s3-1806cc6a21a0.json")

        features = [
            videointelligence.Feature.FACE_DETECTION,
            videointelligence.Feature.OBJECT_TRACKING
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
                     "output_uri": output_uri,
                     "video_context": video_context}
        )

        print(f"\n'{video_name}' 비디오를 처리하고 있습니다...")
        result = operation.result(timeout=timeout)
        print("\n구글 클라우드 분석이 완료됐습니다. 구글 분석 JSON 파일이 만들어졌습니다.")
        print(f"결과가 다음 위치에 저장됐습니다. : {output_uri}")
        return result

    except exceptions.NotFound as e:
        print(f"오류: '{video_name}' 파일을 '{GCS_BUCKET}{INPUT_PREFIX}' 폴더에서 찾을 수 없습니다.")
        print("다음 사항을 확인해 주세요:")
        print("1. 파일 이름이 정확한지 확인하세요.")
        print(f"2. 해당 파일이 실제로 '{GCS_BUCKET}{INPUT_PREFIX}' 폴더에 존재하는지 확인하세요.")
        print("3. 접근 권한이 올바르게 설정되어 있는지 확인하세요.")
    except concurrent.futures.TimeoutError:
        print(f"처리 시간이 {timeout/60:.0f}분을 초과했습니다.")
        print("더 긴 처리 시간이 필요하다면, 관리자에게 문의해 주세요.")
    except exceptions.Forbidden as e:
        print("오류: 이 리소스에 접근할 권한이 없습니다.")
        print("접근 권한 설정을 확인해 주세요. 필요하다면 관리자에게 문의하세요.")
    except exceptions.GoogleAPICallError as e:
        print("API 호출 중 오류가 발생했습니다.")
        print("네트워크 연결을 확인하고, 문제가 지속되면 관리자에게 문의해 주세요.")
    except Exception as e:
        print("예상치 못한 오류가 발생했습니다:")
        print(f"오류 메시지: {e}")
        print("이 오류가 계속되면 관리자에게 문의해 주세요.")

# JSON 병합
def merge_json_files(video_name, gcs_client):
    print("==> merge_json_files")
    aws_output_filename = f"moderation_result.json"
    # input_json_path = os.path.join(AWS_OUTPUT_PREFIX, aws_output_filename)
    # output_json_path = os.path.join(FINAL_OUTPUT_PREFIX, aws_output_filename)
    aws_json_path = f"{AWS_OUTPUT_PREFIX}{aws_output_filename}"
    final_output_path = f"{FINAL_OUTPUT_PREFIX}{aws_output_filename}"

    try:
        # Load AWS output JSON
        aws_output_blob = gcs_client.bucket(GCS_BUCKET.strip("gs://")).blob(aws_json_path)
        aws_output_data = json.loads(aws_output_blob.download_as_text())

         # Create merged JSON
        merged_data = {
            "annotation_results": [
                {"explicit_annotation": aws_output_data}
            ]
        }

        # Load input JSON
        # input_blob = gcs_client.bucket(GCS_BUCKET.strip("gs://")).blob(INPUT_PREFIX + video_name)
        # input_data = json.loads(input_blob.download_as_text())

        # # Merge JSON files
        # if 'annotation_results' in input_data:
        #     input_data['annotation_results'].append({'explicit_annotation': aws_output_data})
        # else:
        #     input_data['annotation_results'] = [{'explicit_annotation': aws_output_data}]

        # Save merged JSON to final output
        # final_output_blob = gcs_client.bucket(GCS_BUCKET.strip("gs://")).blob(output_json_path)
        # final_output_blob.upload_from_string(json.dumps(input_data))

         # Save merged JSON to final output
        final_output_blob = gcs_client.bucket(GCS_BUCKET).blob(final_output_path)
        final_output_blob.upload_from_string(json.dumps(merged_data))

        print(f"최종으로 합쳐진 JSON 파일이 다음 위치에 저장됐습니다. : gs://{GCS_BUCKET}/{final_output_path}")

    except Exception as e:
        print(f"JSON 병합 중 오류 발생: {str(e)}")


# class VideoEventHandler(FileSystemEventHandler):
#     def __init__(self, gcs_client):
#         self.gcs_client = gcs_client

#     def on_modified(self, event):
#         if not event.is_directory:
#             video_name = os.path.basename(event.src_path)
#             output_filename = process_video(video_name)
#             if output_filename:
#                 merge_json_files(video_name, self.gcs_client)

class VideoEventHandler(FileSystemEventHandler):
    def __init__(self, gcs_client):
        self.gcs_client = gcs_client
    
    def on_created(self, event):
        print("==> on_created")
        if not event.is_directory:
            video_name = os.path.basename(event.src_path)
            if self.is_video_file(video_name):
                print(f"새 비디오 파일 감지: {video_name}")
                output_filename = process_video(video_name, self.gcs_client)
                if output_filename:
                    merge_json_files(video_name, self.gcs_client)

    @staticmethod
    def is_video_file(filename):
        video_extensions = ['.3gp', '.avi', '.mov', '.mp4', '.m4v', '.mpeg', '.mpg', '.wmv']
        return any(filename.lower().endswith(ext) for ext in video_extensions)

    # def on_modified(self, event):
    #     if not event.is_directory:
    #         video_name = self.get_latest_video()
    #         if video_name:
    #             output_filename = process_video(video_name)
    #             if output_filename:
    #                 merge_json_files(video_name, self.gcs_client)

    def get_latest_video(self):
        video_files = [f for f in os.listdir(INPUT_PREFIX) if os.path.isfile(os.path.join(INPUT_PREFIX, f))]
        video_files = [f for f in video_files if os.path.splitext(f)[1].lower() in ['.3gp', '.avi', '.mov', '.mp4', '.m4v', '.mpeg', '.mpg', '.wmv']]
        
        if not video_files:
            return None
        
        latest_file = max(video_files, key=lambda x: os.path.getmtime(os.path.join(INPUT_PREFIX, x)))
        return latest_file

def start_observer(gcs_client):
    event_handler = VideoEventHandler(gcs_client)
    observer = Observer()
    observer.schedule(event_handler, path=INPUT_PREFIX, recursive=False)
    print("==> start_observer")
    observer.start()
    try:
        while True:
            print("==> start_observer: TRUE")
            time.sleep(1)
    except KeyboardInterrupt:
        print("==> start_observer: STOP")
        observer.stop()
    observer.join()

# ================================================================================================
if __name__ == "__main__":
    from google.cloud import storage

    # GCS 클라이언트 생성
    gcs_client = storage.Client.from_service_account_json("/Users/highbuff/Downloads/gold-braid-428103-s3-1806cc6a21a0.json")

    print("#####################################################################################")
    print("\nHighbuff 비디오 분석 프로그램입니다.")
    print("주의: 대용량 비디오의 경우 처리 시간이 오래 걸릴 수 있습니다.")
    print("처리 중 프로그램을 중단하지 마세요.")
    print("지원되는 비디오 형식: .3gp, .avi, .mov, .mp4, .m4v, .mpeg, .mpg, .wmv")
    print(f"비디오 파일은 '{GCS_BUCKET}{INPUT_PREFIX}' 폴더에 있어야 합니다.")
    print(f"처리 결과는 '{GCS_BUCKET}{FINAL_OUTPUT_PREFIX}' 폴더에 저장됩니다.")
    print("프로그램을 종료하려면 Ctrl+C를 누르세요.")
    print("#####################################################################################")

    start_observer(gcs_client)
# ================================================================================================