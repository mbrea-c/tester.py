#!/bin/python3
import requests
import math
import json
import matplotlib.pyplot as plt
import os
from tabulate import tabulate
from shapely.geometry import Polygon, Point, LineString

start_lng = -3.186922
start_lat = 55.944871

tests = 0
failed = []
incomplete = []
month_lengths = [31,28,31,30,31,30,31,31,30,31,30,31]


def test(day, month, year):
    sensor_distance = 0.0002
    unit_distance = 0.0003
    epsilon = 0.00001
    forestHill = [-3.192473, 55.946233]
    kfc = [-3.184319, 55.946233]
    meadows = [-3.192473, 55.942617]
    buccleuch = [-3.184319, 55.942617]

    confined_area_poly = Polygon(
        [forestHill, kfc, buccleuch, meadows, forestHill])

    readings_file = open(f'flightpath-{day:02d}-{month:02d}-{year:d}.txt')
    readings = readings_file.readlines()

    # latitude, # longitude
    no_fly_zones = requests.get(
        'http://localhost:9898/buildings/no-fly-zones.geojson').json()

    no_fly_zones_coordinates = [feature['geometry']['coordinates'][0]
                                for feature in no_fly_zones['features']]

    no_fly_polygons = [Polygon(coords) for coords in no_fly_zones_coordinates]

    def is_within_confined_area(point: Point):
        return point.within(confined_area_poly)

    def get_location(w3code):
        coords = requests.get(
            f'http://localhost:9898/words/{w3code}/details.json'
        ).json()['coordinates']

        return Point(coords['lng'], coords['lat'])

    def map_to_sensor_with_location(entry):
        locCode = '/'.join(entry['location'].split('.'))
        entry['code'] = entry['location']
        entry['location'] = get_location(locCode)
        entry['battery'] = float(entry['battery'])
        return entry

    airquality_data = requests.get(
        f'http://localhost:9898/maps/{year}/{month:02d}/{day:02d}/air-quality-data.json').json()

    sensors_with_locations = [
        map_to_sensor_with_location(entry)
        for entry in airquality_data
    ]

    sensors_lookup = dict()

    for sensor in sensors_with_locations:
        sensors_lookup[sensor['code']] = sensor

    def parse_reading(line):
        [move, before_lng, before_lat, angle, after_lng,\
            after_lat, sensor] = line.lstrip().rstrip().split(',')
        move = int(move)
        before_lng = float(before_lng)
        before_lat = float(before_lat)
        angle = int(angle)
        after_lng = float(after_lng)
        after_lat = float(after_lat)

        reading = dict()

        reading['move'] = move
        reading['before'] = Point([before_lng, before_lat])
        reading['after'] = Point([after_lng, after_lat])
        reading['angle'] = angle
        reading['sensor'] = sensor.lstrip().rstrip()

        return reading

    parsed_readings = [parse_reading(line) for line in readings]
    starting_location = parsed_readings[0]['before']

    def intersects_no_fly_zone(pointBefore, pointAfter):
        path_line_string = LineString([pointBefore, pointAfter])
        for poly in no_fly_polygons:
            if path_line_string.intersects(poly):
                return True
        return False

    def get_next_pos_by_angle(previous: Point, angle: int):
        [lng, lat] = previous.coords.xy
        lng = lng[0]
        lat = lat[0]
        angle_radians = math.radians(angle)
        new_lng = lng + math.cos(angle_radians) * unit_distance
        new_lat = lat + math.sin(angle_radians) * unit_distance
        return Point([new_lng, new_lat])

    def distance(x: Point, y: Point):
        [lng, lat] = x.coords.xy
        xlng = lng[0]
        xlat = lat[0]

        [lng, lat] = y.coords.xy
        ylng = lng[0]
        ylat = lat[0]

        return math.sqrt(math.pow(xlng - ylng, 2) + math.pow(xlat - ylat, 2))

    def points_equal(x: Point, y: Point):
        return distance(x, y) <= epsilon

    def is_reading_correct(test_file, current_location: Point, reading: dict):

        move = reading['move']
        before = reading['before']
        after = reading['after']
        angle = reading['angle']
        sensor = reading['sensor']

        if (not is_within_confined_area(before)):
            test_file.write(
                f'before location not in confined area, move: {move}\n')
            return (False, None)
        if (not is_within_confined_area(after)):
            test_file.write(
                f'after location not in confined area, move: {move}\n')
            return (False, None)

        if (not points_equal(current_location, before)):
            test_file.write(f'inconsistent current location in move: {move}\n')
            return (False, None)
        if (not (angle >= 0 and angle < 360) and angle % 10 != 0):
            test_file.write(f'wrong angle in move: {move}\n')
            return (False, None)

        actual_after = get_next_pos_by_angle(current_location, angle)

        if (not points_equal(after, actual_after)):
            test_file.write(f'inconsistent after location in move: {move}\n')
            return (False, None)

        if (intersects_no_fly_zone(before, after)):
            test_file.write(f'intersects no fly zone in move: {move}\n')
            return (False, None)

        sensors = []

        if len(sensor) and '.' in sensor:
            if sensor not in sensors_lookup:
                test_file.write(f'non existent sensor in move: {move}\n')
                return (False, None, sensors)
            else:
                sensor_info = sensors_lookup[sensor]
                sensor_location = sensor_info['location']

                if distance(after, sensor_location) >= sensor_distance:
                    test_file.write(
                        f'tried reading too distant sensor in move: {move}\n'
                    )
                    return (False, None, sensors)
                sensors.append(sensor)

        return (True, after, sensors)

    test_file = open(f'test-{day:02d}-{month:02d}-{year:d}.txt', 'w')
    if len(parsed_readings) > 150:
        test_file.write('more than 150 moves')
        return

    print(f'Testing {day:02d}-{month:02d}-{year:d}...')
    current_location = Point([start_lng, start_lat])

    global tests
    passed = True
    all_sensors = []
    tests += 1
    for reading in parsed_readings:
        (is_correct, next_location, sensors) = is_reading_correct(
            test_file, current_location, reading
        )
        if not is_correct:
            passed = False
            test_file.close()
            break
        else:
            current_location = next_location
            all_sensors += sensors

    if passed:
        if len(all_sensors) == 33 and distance(starting_location, current_location) < unit_distance:
            print(f'Passed {day:02d}-{month:02d}-{year:d}.txt :)')
        else:
            print(f'Incomplete {day:02d}-{month:02d}-{year:d}.txt :)')
            incomplete.append([(day, month, year)])
    else:
        print(f'Failed {day:02d}-{month:02d}-{year:d}.txt :(')
        failed.append([(day, month, year)])


for year in range(2020, 2022):
    for month in range(1, 13):
        for day in range(1, month_lengths[month-1]+1):
            cmd = f'java -jar aqmaps-0.0.1-SNAPSHOT.jar {day:02d} {month:02d} {year} {start_lat} {start_lng} 5678 9898'
            os.system(cmd)
            test(day, month, year)

summary_file = open(f'summary.text', 'w')
summary_file.write(f'tested: {tests}\n')
summary_file.write(f'failed: {failed}\n')
summary_file.write(f'incomplete: {incomplete}\n')
