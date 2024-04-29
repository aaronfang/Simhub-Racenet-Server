from flask import Flask, request, jsonify
import requests
import json
import time
import os
import threading
import logging
import datetime

# 保存JSON文件的时间间隔，单位：秒
SAVE_INTERVAL = 1800

app = Flask(__name__)

# 设置日志级别
logging.basicConfig(level=logging.INFO) # DEBUG, INFO, WARNING, ERROR, CRITICAL

# 设置一个全局的DEBUG变量
DEBUG = False

# 保存access token和refresh token
access_token = ''
refresh_token = ''

# 保存SimHub传递的数据
simhub_data = {}

# 保存从API获取的数据
club_list_data = {}
club_events_data = {}
club_leaderboard_data = {}
time_trial_pre_info = {}
time_trial_leaderboard_data = {}

# 保存最终生成的JSON数据
club_json = {}

# 开始线程
def start_refresh_token_thread():
    refresh_token_thread = threading.Thread(target=do_refresh_token)
    refresh_token_thread.daemon = True
    refresh_token_thread.start()

def start_pre_data_fetching_thread():
    data_fetching_thread = threading.Thread(target=fetch_pre_data)
    data_fetching_thread.daemon = True
    data_fetching_thread.start()

def start_save_json_thread():
    save_json_thread = threading.Thread(target=save_json)
    save_json_thread.daemon = True
    save_json_thread.start()

def fetch_pre_data():
    # Wait for the token to be fetched
    while not access_token:
        time.sleep(1)  # Sleep for a short time to prevent high CPU usage

    # Now that we have the token, we can fetch the data
    get_personal_info(force_update=True)
    get_time_trial_pre_info(force_update=True)
    get_club_list(force_update=True)

############################################################################################
#
# 刷新token的函数
#
############################################################################################
def do_refresh_token():
    global access_token, refresh_token
    # 这里填写你的API信息
    url = "https://web-api.racenet.com/api/identity/refresh-auth"
    headers = {
        'Content-Type': 'application/json',
        'Cookie': f'RACENET-REFRESH-TOKEN={refresh_token}',
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        'charset':'utf-8'
    }
    data = {
        "clientId": "RACENET_1_JS_WEB_APP",
        "grantType": "refresh_token",
        "redirectUri": "https://racenet.com/oauthCallback"
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code == 200:
        result = response.json()
        access_token = result['access_token']
        refresh_token = result['refresh_token']
        # 将新的refresh_token保存到本地文件
        with open('refresh_token.txt', 'w') as f:
            f.write(refresh_token)
        if DEBUG:
            logging.debug(f"Refresh token saved: {refresh_token}")
        # 设置定时器，每隔一段时间刷新token
        try:
            time.sleep((result['expires_in'] - 60))
            do_refresh_token()
        except KeyboardInterrupt:
            print("Program interrupted. Exiting...")
            return

############################################################################################
#
# 接收SimHub数据的路由，包括 clubName, stageID, vehicleID
#
############################################################################################
@app.route('/get_simhub_data/clubName=<clubName>&trackName=<trackName>&vehicleID=<vehicleID>', methods=['GET'])
def get_simhub_data(clubName, trackName, vehicleID):
    global simhub_data
    simhub_data = {
        'clubName': clubName,
        'trackName': trackName,
        'vehicleID': vehicleID
    }
    if DEBUG:
        logging.debug(f"Simhub data received: {simhub_data}")
    
    # Start a new thread to generate the JSON data
    thread = threading.Thread(target=generate_json_data)
    thread.daemon = True
    thread.start()

    return jsonify({'data received': simhub_data}), 200

def generate_json_data():
    generate_time_trial_json()
    generate_club_json()
    
    

############################################################################################
#
# 从本地的racenet_carClasses.json文件中获取信息，创建函数，从输入的vehicleID获取到vehicleClassesID和组别名字
#
############################################################################################
def get_vehicle_classes_info(vehicle_id):
    with open('racenet_carClasses.json', 'r', encoding='utf-8') as f:
        car_classes = json.load(f)
    for vehicle_class_id, vehicle_class in car_classes['vehicleClasses'].items():
        if vehicle_id in vehicle_class['cars']:
            return vehicle_class_id, vehicle_class['class']
    return None, None

def get_stage_info(track_name):
    global time_trial_pre_info
    time_trial_pre_info = get_time_trial_pre_info()
    stage_info = next(((route_id, route_name) for route_id, route_name in time_trial_pre_info['routes'].items() if route_name.lower() in track_name.lower()), (None, None))
    return stage_info[0], stage_info[1]

def get_display_name():
    personal_info = get_personal_info()
    personal_info_json = personal_info
    display_name = personal_info_json.get('displayName', '')
    return display_name

############################################################################################
#
# 获取个人信息：
#
############################################################################################
def get_personal_info(force_update=False):
    # Check if the data is already saved in a local file
    if not force_update and os.path.exists('racenet_personal_info.json'):
        with open('racenet_personal_info.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    # Get the data from the API
    url = "https://web-api.racenet.com/api/identity/secured"
    headers = {
       'Authorization': f'Bearer {access_token}',
       'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = json.loads(response.text)
        # Save the data to a local file
        with open('racenet_personal_info.json', 'w', encoding='utf-8') as f:
            json.dump(data, f)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Personal info saved to: racenet_personal_info.json")
        return data
    else:
        print(f"Error: {response.status_code}")
        return None

############################################################################################
#
# 获取俱乐部的信息：
#
############################################################################################
# 获取俱乐部列表的函数
def get_club_list(force_update=False):
    global club_list_data
    take = 20
    skip = 0
    club_list_data = {'totalActiveMemberships': 0, 'activeMemberships': []}

    # Check if the data is already saved in a local file
    if not force_update and os.path.exists('racenet_club_list_data.json'):
        with open('racenet_club_list_data.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    while True:
        url = f"https://web-api.racenet.com/api/wrc2023clubs/memberships/active?take={take}&skip={skip}&includeChampionship=true"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            try:
                data = response.json()
                club_list_data['totalActiveMemberships'] = data['totalActiveMemberships']
                club_list_data['activeMemberships'].extend(data['activeMemberships'])
                if len(data['activeMemberships']) < take:
                    break
                else:
                    skip += take
            except json.JSONDecodeError:
                print("Error: Response is not valid JSON")
                print("Response: ", response.text)
        else:
            print(f"Error: {response.status_code}")
            print("Response: ", response.text)
            break

    # Save the data to a local file
    with open('racenet_club_list_data.json', 'w', encoding='utf-8') as f:
        json.dump(club_list_data, f, ensure_ascii=False)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Club list data saved to: racenet_club_list_data.json")

    if DEBUG:
        logging.debug(f"Club list data: {club_list_data}")

    return club_list_data


# 根据clubName找到匹配的clubID，然后获取该club所有赛事列表的函数
def get_club_events():
    global club_list_data, simhub_data, club_events_data

    club_list_data = get_club_list()
    # Find the club ID from the club list data
    club_id = next((item['clubID'] for item in club_list_data['activeMemberships'] if item['clubName'] == simhub_data['clubName']), None)
    if club_id is None:
        print("Club not found")
        return

    # Get the club events
    url = f"https://web-api.racenet.com/api/wrc2023clubs/{club_id}?includeChampionship=true"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            club_events_data = response.json()
            if DEBUG:
                logging.debug(f"Club events data: {club_events_data}")
        else:
            print(f"Error: {response.status_code}")
            return
    except Exception as e:
        print(f"An error occurred while getting club events: {e}")

# 基于上一步取得的"该club所有赛事列表",再根据我们传递的stageID对应到数据中的routeID，从而获取到对应的leaderboardID，再通过这个leaderboardID获取到当前赛事的排行榜数据
def get_club_leaderboard(vehicle_class_id, stage_id):
    global club_events_data, club_leaderboard_data

    # # Get the vehicle class ID
    # vehicle_class_id, _ = get_vehicle_classes_info(simhub_data['vehicleID'])

    # # Get the stage ID
    # stage_id, stage_name = get_stage_info(simhub_data['trackName'])

    # Find the event ID from the club events data
    leaderboard_ids = [stage['leaderboardID'] for event in club_events_data['currentChampionship']['events'] for stage in event['stages'] if str(stage['stageSettings']['routeID']) == str(stage_id) and str(event['eventSettings']['vehicleClassID']) == str(vehicle_class_id)]
    if len(leaderboard_ids) > 1:
        print("Warning: Multiple leaderboard with same stage in this club. Using the first one.")
    leaderboard_id = leaderboard_ids[0] if leaderboard_ids else None

    club_leaderboard_data = {'entries': []}
    cursor = None

    while True:
        try:
            # Get the leaderboard data
            url = f"https://web-api.racenet.com/api/wrc2023clubs/{club_events_data['clubID']}/leaderboard/{leaderboard_id}?SortCumulative=false&MaxResultCount=20&FocusOnMe=false&Platform=0"
            if cursor:
                url += f"&Cursor={cursor}"
            headers = {
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
            }
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                club_leaderboard_data['entries'].extend(data['entries'])
                cursor = data.get('next')  # Assuming 'nextCursor' is the key for the next cursor
                if not cursor or not data['entries']:
                    break
            else:
                print(f"Error: {response.status_code}")
                break
        except Exception as e:
            print(f"An error occurred while getting leaderboard data: {e}")
            break

    if DEBUG:
        logging.debug(f"vehicle_class_id: {vehicle_class_id}, stage_id: {stage_id}, leaderboard_id: {leaderboard_id}")
        logging.debug(f"Club leaderboard data: {club_leaderboard_data}") 

# 生成最终的JSON数据的函数，从get_club_events函数中，根据当前stageID，获取leaderboardID，route（赛段名称），weatherAndSurface，timeOfDay，serviceArea，distance
# 基于“当前赛事的排行榜数据”，分析出：rank, displayName, time, differenceToFirst, nationalityID, timePenalty, vehicle, points
# 合并成一个club_json字典，然后保存到本地文件
def generate_club_json():
    global club_json, club_events_data, club_leaderboard_data, simhub_data

    # Call the necessary functions to get the data
    # get_club_list()
    get_club_events()    

    # Get personal info
    myName = get_display_name()

    # Get the vehicle class ID，vehicle class name. stage ID
    vehicle_class_id, vehicle_class_name = get_vehicle_classes_info(simhub_data['vehicleID'])

    # Get the stage ID
    stage_id, stage_name = get_stage_info(simhub_data['trackName'])

    get_club_leaderboard(vehicle_class_id, stage_id)

    # Find the stage from the club events data
    stage = next((stage for event in club_events_data['currentChampionship']['events'] for stage in event['stages'] if str(stage['stageSettings']['routeID']) == str(stage_id)), None)
    if stage is None:
        # print('Try to find stageID: ' + stage_id + ' and stageName: ' + stage_name + ' in club_events_data. But found routeID: ' + stage['stageSettings']['routeID'])
        print("Stage not found")
        return

    # Generate the final JSON for all leaderboard entries
    leaderboard_entries = []
    for leaderboard_entry in club_leaderboard_data['entries']:
        leaderboard_entries.append({
            'rank': leaderboard_entry['rank'],
            'displayName': leaderboard_entry['displayName'],
            'time': leaderboard_entry['time'],
            'differenceToFirst': leaderboard_entry['differenceToFirst'],
            'nationalityID': leaderboard_entry['nationalityID'],
            'timePenalty': leaderboard_entry['timePenalty'],
            'vehicle': leaderboard_entry['vehicle'],
            'points': leaderboard_entry['points']
        })

    club_json = {
        'myName': myName,
        'clubName': club_events_data['clubName'],
        'clubID': club_events_data['clubID'],
        'leaderboardID': stage['leaderboardID'],
        'stageID': stage_id,
        'route': stage['stageSettings']['route'],
        'vehicleClassID': vehicle_class_id,
        'vehicleClassName': vehicle_class_name,
        'weatherAndSurface': stage['stageSettings']['weatherAndSurface'],
        'timeOfDay': stage['stageSettings']['timeOfDay'],
        'serviceArea': stage['stageSettings']['serviceArea'],
        'distance': stage['stageSettings']['distance'],
        'lastUpdated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'leaderboardEntries': leaderboard_entries
    }
    # club_json['leaderboardEntries'] = leaderboard_entries

    # Check if the necessary data exists
    if 'clubID' in club_json and 'leaderboardID' in club_json:
        # Save the JSON data to a file
        filename = f'racenet_club.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(club_json, f, ensure_ascii=False)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - JSON data saved to: {filename}")
    else:
        print("No data to save.")

############################################################################################
#
# 获取计时赛的信息：
#
############################################################################################
# 首先通过API获取计时赛前置信息，包括routeID，vehicleClassesID，vehicleID，surfaceConditionID
def get_time_trial_pre_info(force_update=False):
    # Check if the data is already saved in a local file
    if not force_update and os.path.exists('racenet_time_trial_pre_info.json'):
        with open('racenet_time_trial_pre_info.json', 'r', encoding='utf-8') as f:
            return json.load(f)

    # If not, get the data from the API
    url = "https://web-api.racenet.com/api/wrc2023Stats/values"
    headers = {
       'Authorization': f'Bearer {access_token}',
       'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Save the data to a local file
            with open('racenet_time_trial_pre_info.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Time trial pre-info saved to: racenet_time_trial_pre_info.json")
            return data
        else:
            print(f"Error: {response.status_code}")
            print("Response: ", response.text)
            return None
    except Exception as e:
        print(f"An error occurred while getting time trial pre-info: {e}")
        return None

# 然后根据已知的stageID，vehicleClassesID 以及surfaceConditionID（0,1）获取到当前赛道的排行榜数据
def get_time_trial_leaderboard(stage_id, vehicle_class_id, surface_condition_id, max_page=1):
    global access_token, time_trial_leaderboard_data

    url = f"https://web-api.racenet.com/api/wrc2023Stats/leaderboard/{stage_id}/{vehicle_class_id}/{surface_condition_id}?maxResultCount=20&focusOnMe=false&platform=0&cursor"
    headers = {
       'Authorization': f'Bearer {access_token}',
       'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'
    }

    time_trial_leaderboard_data = {'entries': []}
    cursor = None
    pages_fetched = 0

    while True:
        if cursor:
            url += f"&Cursor={cursor}"
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                time_trial_leaderboard_data['entries'].extend(data['entries'])
                cursor = data.get('next')  # Assuming 'nextCursor' is the key for the next cursor
                pages_fetched += 1
                if not cursor or not data['entries'] or pages_fetched >= max_page:
                    break
            else:
                print(f"Error: {response.status_code}")
                break
        except Exception as e:
            print(f"An error occurred while getting leaderboard data: {e}")
            break

    # # Fetch the user's own leaderboard data
    # url = f"https://web-api.racenet.com/api/wrc2023Stats/leaderboard/{stage_id}/{vehicle_class_id}/{surface_condition_id}?maxResultCount=20&focusOnMe=true&platform=0&cursor"
    # try:
    #     response = requests.get(url, headers=headers)
    #     if response.status_code == 200:
    #         data = response.json()
    #         if data['entries']:
    #             time_trial_leaderboard_data['entries'].append(data['entries'][0])  # Assuming the user's data is the first entry
    #         else:
    #             print("User's data not found")
    # except Exception as e:
    #     print(f"An error occurred while getting user's leaderboard data: {e}")

    if DEBUG:
        logging.debug(f"Time trial leaderboard data for {surface_condition_id} condition: {time_trial_leaderboard_data}")

    return time_trial_leaderboard_data

# 获取到当前赛道的排行榜数据(比如：rank, displayName, time, differenceToFirst, nationalityID, timePenalty, vehicle, splits)
def generate_time_trial_json():
    global simhub_data, time_trial_leaderboard_data

    # Get personal info
    myName = get_display_name()

    # Get the vehicle class ID and name
    vehicle_class_id, vehicle_class_name = get_vehicle_classes_info(simhub_data['vehicleID'])

    # Get the stage ID
    stage_id, stage_name = get_stage_info(simhub_data['trackName'])

    # Generate JSON for dry and wet conditions
    for surface_condition_id, condition in [(0, 'dry'), (1, 'wet')]:
        leaderboard_entries = []
        get_time_trial_leaderboard(stage_id, vehicle_class_id, surface_condition_id, max_page=1)
        if time_trial_leaderboard_data:
            # Generate the final JSON for all leaderboard entries
            for leaderboard_entry in time_trial_leaderboard_data['entries']:
                leaderboard_entries.append({
                    'rank': leaderboard_entry['rank'],
                    'displayName': leaderboard_entry['displayName'],
                    'time': leaderboard_entry['time'],
                    'differenceToFirst': leaderboard_entry['differenceToFirst'],
                    'nationalityID': leaderboard_entry['nationalityID'],
                    'timePenalty': leaderboard_entry['timePenalty'],
                    'vehicle': leaderboard_entry['vehicle'],
                    'splits': leaderboard_entry['splits']
                })

        time_trial_json = {
            'myName': myName,
            'stageID': stage_id,
            'route': stage_name,
            'vehicleClassID': vehicle_class_id,
            'vehicleClassName': vehicle_class_name,
            'surfaceCondition': condition,
            'lastUpdated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'leaderboardEntries': leaderboard_entries
        }

        # Save the JSON data to a file
        filename = f'racenet_time_trial_{condition}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(time_trial_json, f, ensure_ascii=False)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - JSON data saved to: {filename}")

############################################################################################
# 
# 循环保存JSON文件
# 
############################################################################################
def save_json_periodically():
    global SAVE_INTERVAL, simhub_data
    last_save_time = time.time()
    while True:
        if simhub_data and time.time() - last_save_time >= SAVE_INTERVAL:
            generate_time_trial_json()
            generate_club_json()
            last_save_time = time.time()
        time.sleep(1)  # Sleep for a short time to prevent high CPU usage

def save_json():
    if simhub_data:
        generate_time_trial_json()
        generate_club_json()

if __name__ == '__main__':
    # 如果存在refresh_token.txt文件，就从文件中读取refresh_token
    if os.path.exists('refresh_token.txt'):
        with open('refresh_token.txt', 'r') as f:
            refresh_token = f.read()
    else:
        refresh_token = input("Please enter a valid refresh token: ")

    start_refresh_token_thread()
    start_pre_data_fetching_thread()
    start_save_json_thread()

    app.run(port=5000)