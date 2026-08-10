# This will block and stream data broadcasts from all visible RuuviTag sensors nearby
def handle_data(found_data):
    mac = found_data[0]
    sensor_data = found_data[1]
    print(f"MAC: {mac}, Temp: {sensor_data['temperature']}°C, Humidity: {sensor_data['humidity']}%")

if __name__ == '__main__':
    # Start listening to broadcasts from all tags
    RuuviTagSensor.listen(handle_data)