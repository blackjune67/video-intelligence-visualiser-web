console.log('IMPORTING OBJECT TRACKING')

// define style rules to be programtically loaded
var style = document.createElement('style');
style.innerHTML = `

@import url(https://fonts.googleapis.com/css?family=Roboto);

.segment-timeline{
    
    width: 100%;
    position: relative; 
    height: 1em;
}

.segment-container{
    text-align: center;
    margin:10px;
}

.segment{
    position: absolute; 
    background-color: #fc9b03;
    height: 1em;
    border-radius: 5px;
    min-width: 5px;
    cursor: pointer;
}

.label{
    display: inline-block;
    background-color:  #fc9b03;
    color: white;
    padding: 5px;
    font-size: 1.1em;
    vertical-align: middle;
    width: 10%;
    min-width: 190px;
    border-radius: 5px;
}



.segment-timeline{
    display: inline-block;
    vertical-align: middle;
    width: 80%;
    background-color: #f5f5f5;
    padding: 5px;
    border-radius: 5px;
}




.segments-enter-active, .segments-leave-active , .segment-container{
    transition: all 0.2s;
  }

.segments-enter, .segments-leave-to /* .list-leave-active below version 2.1.8 */ {
    opacity: 0;
    transform: translateY(30px);
}


.confidence {
    text-align: center;
    margin: 20px;
    font-size: 1.2em;
}

.confidence > input {
    width: 300px;
    vertical-align: middle;
}

.confidence > .confidence-value{
    display: inline-block;
    text-align: left;
    width: 60px;
}

.time-ticker{
    height:100%;
    width: 1px;
    background-color: gray;
}

`;
document.getElementsByTagName('head')[0].appendChild(style);


// define component
Vue.component('object-tracking-viz', {
    props: ['json_data', 'video_info'],
    data: function () {
        return {
            confidence_threshold: 0.5,
            interval_timer: null,
            ctx: null
        }
    },
    computed: {
        object_tracks: function () {
            `
            Extract just the object tracking data from json
            `

            if (!this.json_data.annotation_results)
                return []

            for (let index = 0; index < this.json_data.annotation_results.length; index++) {
                if ('object_annotations' in this.json_data.annotation_results[index])
                    return this.json_data.annotation_results[index].object_annotations
            }
            return []
        },

        indexed_object_tracks: function () {
            `
            Create a clean list of object tracking data with realisied nullable fields 
            and scaled bounding boxes ready to be drawn by the canvas
            `

            const indexed_tracks = []

            this.object_tracks.forEach(element => {
                if (element.confidence > this.confidence_threshold)
                    indexed_tracks.push(new Object_Track(element, this.video_info.height, this.video_info.width))
            })

            return indexed_tracks
        },

        object_track_segments: function () {
            ` 
            create the list of cronological time segments that represent just when objects are present on screen
            `
            const segments = {}

            this.indexed_object_tracks.forEach(object_tracks => {

                if (!(object_tracks.name in segments))
                    segments[object_tracks.name] = {'segments': [], 'count': 0}

                segments[object_tracks.name].count++

                var added = false

                for (let index = 0; index < segments[object_tracks.name].length; index++) {

                    const segment = segments[object_tracks.name].segments[index]
                    if (object_tracks.start_time < segment[1]) {
                        segments[object_tracks.name].segments[index][1] = Math.max(segments[object_tracks.name].segments[index][1], object_tracks.end_time)
                        added = true
                        break
                    }
                }

                if (!added)
                    segments[object_tracks.name].segments.push([object_tracks.start_time, object_tracks.end_time])
            })

            return segments
        }
    },
    methods: {
        segment_style: function (segment) {
            return {
                left: ((segment[0] / this.video_info.length) * 100).toString() + '%',
                width: (((segment[1] - segment[0]) / this.video_info.length) * 100).toString() + '%'
            }
        },
        segment_clicked: function (segment_data) {
            this.$emit('segment-clicked', {seconds: segment_data[0] - 0.5})
        }
    },
    template: `
    <div calss="object-tracking-container">
        
        <div class="confidence">
            <span>신뢰도 임계값</span>
            
            <input type="range" style="accent-color: #fc9b03;" min="0.0" max="1" value="0.5" step="0.01" v-model="confidence_threshold">
            <span class="confidence-value">{{confidence_threshold}}</span>
            <br>
            <pre style="font-size: medium">
            반환할 예측을 결정하는 신뢰도 점수입니다. 모델이 이 값 이상인 예측을 반환합니다. 신뢰도 기준점이 높을수록 정밀도는 높아지지만 재현율이 낮아집니다.
            </pre>
        </div>
        
        <!--<div class="confidence">
            <div class="confidence-label">
                <span>정확성</span><br>
                <small class="confidence-description">(값을 높일수록 정확한 사물을 판단합니다.)</small>
            </div>
                <input class="confidence-slider" type="range" min="0.0" max="1" value="0.5" step="0.01" v-model="confidence_threshold">
                <span class="confidence-value">{{confidence_threshold}}</span>      
        </div>-->

        <div class="data-warning" v-if="object_tracks.length == 0">JSON파일에 정의된 오브젝트 데이터가 없습니다.</div>

        <transition-group name="segments" tag="div">
            
            <div class="segment-container" v-for="segments, key in object_track_segments" v-bind:key="key + 'z'">
                <div class="label">{{key}} ({{segments.count}})</div>
                <div class="segment-timeline">
                    <div class="segment" v-for="segment in segments.segments" 
                                        v-bind:style="segment_style(segment)" 
                                        v-on:click="segment_clicked(segment)"
                    ></div>
                </div>
            </div>
        </transition-group>
    </div>
    `,
    mounted: function () {
        console.log('mounted component')
        var canvas = document.getElementById("my_canvas")
        this.ctx = canvas.getContext("2d")
        this.ctx.font = "20px Roboto"
        const ctx = this.ctx

        const component = this

        this.interval_timer = setInterval(function () {
            // console.log('running')
            const object_tracks = component.indexed_object_tracks

            draw_bounding_boxes(object_tracks, ctx)
        }, 1000 / 30)
    },
    beforeDestroy: function () {
        console.log('destroying component')
        clearInterval(this.interval_timer)
        this.ctx.clearRect(0, 0, 800, 500)
    }
})


class Object_Track {
    constructor(json_data, video_height, video_width) {
        this.name = json_data.entity.description
        this.start_time = nullable_time_offset_to_seconds(json_data.segment.start_time_offset)
        this.end_time = nullable_time_offset_to_seconds(json_data.segment.end_time_offset)
        this.confidence = json_data.confidence

        this.frames = []

        json_data.frames.forEach(frame => {
            const new_frame = {
                'box': {
                    'x': (frame.normalized_bounding_box.left || 0) * video_width,
                    'y': (frame.normalized_bounding_box.top || 0) * video_height,
                    'width': ((frame.normalized_bounding_box.right || 0) - (frame.normalized_bounding_box.left || 0)) * video_width,
                    'height': ((frame.normalized_bounding_box.bottom || 0) - (frame.normalized_bounding_box.top || 0)) * video_height
                },
                'time_offset': nullable_time_offset_to_seconds(frame.time_offset)
            }
            this.frames.push(new_frame)
        })
    }

    has_frames_for_time(seconds) {
        return ((this.start_time <= seconds) && (this.end_time >= seconds))
    }

    most_recent_real_bounding_box(seconds) {

        for (let index = 0; index < this.frames.length; index++) {
            if (this.frames[index].time_offset > seconds) {
                if (index > 0)
                    return this.frames[index - 1].box
                else
                    return null
            }
        }
        return null
    }

    most_recent_interpolated_bounding_box(seconds) {

        for (let index = 0; index < this.frames.length; index++) {
            if (this.frames[index].time_offset > seconds) {
                if (index > 0) {
                    if ((index == 1) || (index == this.frames.length - 1))
                        return this.frames[index - 1].box

                    // create a new interpolated box between the 
                    const start_box = this.frames[index - 1]
                    const end_box = this.frames[index]
                    const time_delt_ratio = (seconds - start_box.time_offset) / (end_box.time_offset - start_box.time_offset)

                    const interpolated_box = {
                        'x': start_box.box.x + (end_box.box.x - start_box.box.x) * time_delt_ratio,
                        'y': start_box.box.y + (end_box.box.y - start_box.box.y) * time_delt_ratio,
                        'width': start_box.box.width + (end_box.box.width - start_box.box.width) * time_delt_ratio,
                        'height': start_box.box.height + (end_box.box.height - start_box.box.height) * time_delt_ratio
                    }
                    return interpolated_box

                } else
                    return null
            }
        }
        return null
    }

    current_bounding_box(seconds, interpolate = true) {

        if (interpolate)
            return this.most_recent_interpolated_bounding_box(seconds)
        else
            return this.most_recent_real_bounding_box(seconds)
    }
}