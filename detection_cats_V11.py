import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import numpy as np
import cv2
import hailo
from hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
    app_callback_class,
)
from detection_pipeline import GStreamerDetectionApp
from paho.mqtt import client as mqtt_client

from datetime import datetime
import time

# MQTT Credentials for Homeassistant
broker = '192.168.178.65'
port = 1883
topic = "catcam/state"
# Generate a Client ID with the publish prefix.
client_id = f'publish-100'
#client_id = f'publish-{random.randint(0, 1000)}'
username = 'mqtt-user'
password = 'DerMQTTServer1'

# RTSP Server Credentials for RPI4
rtsp_server = '192.168.178.37'

# connect to Homeassistant
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            publish(client, "none")
        else:
            print("Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client(client_id)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

# publish dertected item to homeassistant
def publish(client, msg):
    result = client.publish(topic, msg)
    # result: [0, 1]
    status = result[0]
    if status == 0:
        print(f"Send `{msg}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")


# -----------------------------------------------------------------------------------------------
# User-defined class to be used in the callback function
# -----------------------------------------------------------------------------------------------
# Inheritance from the app_callback_class
class user_app_callback_class(app_callback_class):
    def __init__(self):
        super().__init__()
        self.new_variable = 42  # New variable example
        self.new_detection = 0  # New variable example

    def current_time(self):  # New function example
        # datetime object containing current date and time
        now = datetime.now()
 
        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        return (dt_string)
        

# -----------------------------------------------------------------------------------------------
# User-defined callback function
# -----------------------------------------------------------------------------------------------

# This is the callback function that will be called when data is available from the pipeline
def app_callback(pad, info, user_data):
    # Get the GstBuffer from the probe info
    buffer = info.get_buffer()
    # Check if the buffer is valid
    if buffer is None:
        return Gst.PadProbeReturn.OK

    # Using the user_data to count the number of frames
    user_data.increment()
    string_to_print = f"Frame count: {user_data.get_count()}\n"

    # Get the caps from the pad
    format, width, height = get_caps_from_pad(pad)

    # If the user_data.use_frame is set to True, we can get the video frame from the buffer
    frame = None
    if user_data.use_frame and format is not None and width is not None and height is not None:
        # Get video frame
        frame = get_numpy_from_buffer(buffer, format, width, height)

    # Get the detections from the buffer
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    # Parse the detections
    detection_count = 0
    label_detected = "none"
    my_x_min = []
    my_y_min =[]
    my_x_max = []
    my_y_max =[]
    
    for detection in detections:
        label = detection.get_label()
        bbox = detection.get_bbox()
        confidence = detection.get_confidence()
        prev_count = detection_count
        if label == "cat" and confidence > 0.35:
            #string_to_print += f"Detection: {label} {confidence:.2f}\n"
            # Call the coordinate methods
            my_x_min.append(bbox.xmin()*640)
            my_y_min.append(bbox.ymin()*640)
            my_x_max.append((bbox.xmin()*640 + bbox.width()*640))
            my_y_max.append((bbox.ymin()*640 + bbox.height()*640))
            
            detection_count += 1
            label_detected = (f" {label} Anzahl: {detection_count}")
        else:
            label_detected = "none"
    
    if user_data.use_frame:
        # Note: using imshow will not work here, as the callback function is not running in the main thread
        # Let's print the detection count to the frame
        cv2.putText(frame, f"{user_data.current_time()}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        # Example of how to use the new_variable and new_function from the user_data
        # Let's print the new_variable and the result of the new_function to the frame
        cv2.putText(frame, f"Objekt: {label_detected}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        for x in range(len(my_x_min)):
            cv2.rectangle(frame, (int((my_x_min[x])), int((my_y_min[x]))), (int((my_x_max[x])), int((my_y_max[x]))), (0, 0, 255), 2)  
        # Convert the frame to BGR
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # output frame to screen
        user_data.set_frame(frame)
       
               
        # send detection to MQTT and take picture
        if user_data.new_detection != detection_count:
            publish(client, label_detected)
            if (label_detected != "none"):
                cv2.imwrite('/home/StephanS/fritzNAS/Bilder/imagedetected.jpg', frame)
                #print(f"Picture of detected object saved")
                time.sleep(1) # wait for 1 second
            user_data.new_detection = detection_count
            
    #print(string_to_print)
    return Gst.PadProbeReturn.OK

if __name__ == "__main__":
    # connect to homeassistant
    client = connect_mqtt()
    client.loop_start()
    #client.loop_stop()
    # Create an instance of the user app callback class
    user_data = user_app_callback_class()
    app = GStreamerDetectionApp(app_callback, user_data)
    
    app.run()
