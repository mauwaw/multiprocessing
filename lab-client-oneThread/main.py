import multiprocessing
import threading
from multiprocessing import Queue

from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
import requests
import logging
import time

app = FastAPI()

logging.basicConfig(handlers=[
    logging.StreamHandler()
],
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)

global Help
Help = {
    'HUM_COUNT': 0,
    'HUM_MODE': 1,
    'HUM_AVG': 2,
    'TEMP_COUNT': 3,
    'TEMP_MODE': 4,
    'TEMP_AVG': 5,
    'LIGHT_COUNT': 6,
    'LIGHT_MODE': 7,
    'LIGHT_AVG': 8,
    'PRESS_COUNT': 9,
    'PRESS_MODE': 10,
    'PRESS_AVG': 11,
    'PREC_COUNT': 12,
    'PREC_MODE': 13,
    'PREC_AVG': 14,
}

Type = {
    'HUM': 0,
    'TEMP': 1,
    'LIGHT': 2,
    'PRESS': 3,
    'PREC': 4
}

class SensorDataEntry(BaseModel):
    data_type: str
    day: int
    val: int


class Handshake(BaseModel):
    ip_addr: str
    port: int


SERVER_IP = 'localhost'
SERVER_PORT = 5670

CLIENT_IP = 'localhost'
CLIENT_PORT = 6780

INDEKS = 450733

def function(queue : Queue):

    result = multiprocessing.Array('d', [0] * 500000)  # Shared array for results
    day_readings = multiprocessing.Array('f', [0] * 500)  # Shared array for day readings
    day_mode = multiprocessing.Array('f', [0] * (21 * 500))  # Shared array for day mode data
    days_lock = multiprocessing.Lock()
    mode_lock = multiprocessing.Lock()
    result_loc = multiprocessing.Lock()
    readings_lock = multiprocessing.Lock()
    # Using Manager to create shared data structures for more complex data types
    manager = multiprocessing.Manager()
    days = manager.list()  # Shared set for tracking days

    DATA_TYPES = ['HUM', 'TEMP', 'LIGHT', 'PRESS', 'PREC']

    number_of_wokers = 2

    workers = [multiprocessing.Process(target=process, args=(queue, days, result, day_readings, day_mode, days_lock, readings_lock, mode_lock, result_loc)) for i in range(0,number_of_wokers)] # w docelowym rozwiązaniu musisz zastosować multiprocessing.Process
    start_time = time.time()
    for w in workers:
        w.start()

    for w in workers:
        w.join()

    wynik = []
    
    for dzien in range(0, len(days)):
        for type in DATA_TYPES:
            result[Help.get(type + '_AVG') + dzien * len(Help)] /= (float(day_readings[dzien]) / float(len(DATA_TYPES)))
            maksimal = 0
            wy = 0
            for i in range(21):
                if maksimal <  day_mode[(Type.get(type) + dzien*len(Type))*21 +i]: 
                    maksimal = day_mode[(Type.get(type) + dzien*len(Type))*21 +i]
                    wy = i
            result[Help.get(type + '_MODE') + dzien*len(Help)] = wy

    # wypisanie wyniku w formie w której serwer jej oczekuje
    # process zapisuje dane w tabeli pod indeksami po 20 indeksów na dzień w kolejności jak poniżej
    # ponieważ tak jest najbardziej wydajnie
    for dd in range(0, len(days)):
        dzien = {'day': dd,
                 'HUM_COUNT': result[dd*len(Help) + Help.get('HUM_COUNT')],
                 'HUM_MODE': result[dd*len(Help) + Help.get('HUM_MODE')],
                 'HUM_AVG': result[dd*len(Help) + Help.get('HUM_AVG')],
                 'TEMP_COUNT': result[dd*len(Help) + Help.get('TEMP_COUNT')],
                 'TEMP_MODE': result[dd*len(Help) + Help.get('TEMP_MODE')],
                 'TEMP_AVG': result[dd*len(Help) + Help.get('TEMP_AVG')],
                 'LIGHT_COUNT': result[dd*len(Help) + Help.get('LIGHT_COUNT')],
                 'LIGHT_MODE': result[dd*len(Help) + Help.get('LIGHT_MODE')],
                 'LIGHT_AVG': result[dd*len(Help) + Help.get('LIGHT_AVG')],
                 'PRESS_COUNT': result[dd*len(Help) + Help.get('PRESS_COUNT')],
                 'PRESS_MODE': result[dd*len(Help) + Help.get('PRESS_MODE')],
                 'PRESS_AVG': result[dd*len(Help) + Help.get('PRESS_AVG')],
                 'PREC_COUNT': result[dd*len(Help) + Help.get('PREC_COUNT')],
                 'PREC_MODE': result[dd*len(Help) + Help.get('PREC_MODE')],
                 'PREC_AVG': result[dd*len(Help) + Help.get('PREC_AVG')]}
        wynik.append(dzien)

    requests.post(f"http://{SERVER_IP}:{SERVER_PORT}/results",
                  json={"ip_addr": CLIENT_IP, "port": CLIENT_PORT, "indeks": INDEKS, "aggregates": wynik})
    end_time = time.time()
    elapsed_time = end_time - start_time
    logging.info(f"Czas wykonania: {elapsed_time:.2f} sekund")

import logging
from collections import defaultdict
from multiprocessing import current_process, Process, Queue
from queue import Empty

# Configure logging
# logging.basicConfig(level=logging.DEBUG, format='%(processName)s - %(levelname)s - %(message)s')

def process(queue, days, result, day_readings, day_mode, days_lock, result_lock, readings_lock, mode_lock):
    process_name = current_process().name
    local_days = set()
    local_day_readings = defaultdict(float)
    local_day_mode = defaultdict(float)
    local_result = defaultdict(float)

    logging.debug(f"{process_name}: Process started.")
    countitem = 0
    while True:
        try:
            data = queue.get_nowait()
            # logging.debug(f"{process_name}: Data retrieved from queue: {data}")
        except Empty:
            logging.debug(f"{process_name}: Queue is empty, stopping process.")
            break
        countitem += 1
        # Collect local days
        local_days.add(data.day)
        # logging.debug(f"{process_name}: Added day to local_days: {data.day}")
        
        # Update local day_readings
        local_day_readings[data.day] += 1
        # logging.debug(f"{process_name}: Updated local_day_readings for day {data.day}: {local_day_readings[data.day]}")

        # Update local day_mode
        key = (Type.get(data.data_type) + data.day * len(Type)) * 21 + data.val
        local_day_mode[key] += 1
        # logging.debug(f"{process_name}: Updated local_day_mode for key {key}: {local_day_mode[key]}")

        # Update local result
        local_result[Help.get(data.data_type + '_COUNT') + data.day * len(Help)] += 1
        local_result[Help.get(data.data_type + '_AVG') + data.day * len(Help)] += data.val
        # logging.debug(f"{process_name}: Updated local_result for keys COUNT and AVG: {local_result}")

    # Combine local results into shared data structures
    # logging.debug(f"{process_name}: Combining local results into shared data structures.")

    # Lock for modifying the days list
    with days_lock:
        for day in local_days:
            if day not in days:
                days.append(day)
                # logging.debug(f"{process_name}: Added day to shared days list: {day}")

    # Lock for modifying day_readings
    with readings_lock:
        for day, count in local_day_readings.items():
            day_readings[day] += count
            # logging.debug(f"{process_name}: Updated shared day_readings for day {day}: {day_readings[day]}")

    # Lock for modifying day_mode
    with mode_lock:
        for key, count in local_day_mode.items():
            day_mode[key] += count
            # logging.debug(f"{process_name}: Updated shared day_mode for key {key}: {day_mode[key]}")

    # Lock for modifying result
    with result_lock:
        for key, value in local_result.items():
            result[key] += value
            # logging.debug(f"{process_name}: Updated shared result for key {key}: {result[key]}")

    logging.debug(f"{process_name}: Process completed, items:{countitem}")


# nie zmieniać
@app.post("/sensor-data", status_code=201)
async def create_sensor_data(sensor_data_entry: List[SensorDataEntry]):
    queue = multiprocessing.Queue()
    for el in sensor_data_entry:
        queue.put(el)
    logging.info('Processing')
    res = threading.Thread(target=function, args=(queue,), daemon=True)
    res.start()

@app.get("/hello")
async def say_hello():
    res = requests.post(f"http://{SERVER_IP}:{SERVER_PORT}/clients/handshake",
                        json={"ip_addr": CLIENT_IP, "port": CLIENT_PORT, "indeks": INDEKS})
    if (res.status_code == 201):
        return "Success"
    else:
        return f"Error occurred {res.text}"
