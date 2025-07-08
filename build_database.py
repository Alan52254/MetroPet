# build_database.py
import os
import json
import re
import time
import config
from services.tdx_service import tdx_api # 確保 tdx_api 已被匯入

def normalize_name(name: str) -> str:
    """標準化站點名稱：小寫、移除括號內容、移除「站」、繁轉簡"""
    if not name: return ""
    name = name.lower().strip().replace("臺", "台")
    name = re.sub(r"[\(（].*?[\)）]", "", name).strip()
    if name.endswith("站"): name = name[:-1]
    return name

def build_station_database():
    """
    從 TDX API 獲取所有捷運站點資訊，並儲存為 JSON 檔案。
    """
    print("\n--- [1/4] 正在建立「站點資料庫」... ---")
    all_stations_data = tdx_api.get_mrt_network() # 【修正】現在這個函式存在了！
    if not all_stations_data:
        print("--- ❌ 步驟 1 失敗: 無法獲取車站資料。請檢查 API 金鑰與網路。 ---")
        return

    station_map = {}
    # 手動加入一些常見別名對照
    alias_map = {"北車": "台北車站", "101": "台北101/世貿"}

    for route in all_stations_data:
        for station in route.get("Stations", []):
            zh_name = station.get("StationName", {}).get("Zh_tw")
            en_name = station.get("StationName", {}).get("En")
            station_id = station.get("StationID")

            if zh_name and station_id:
                # 收集所有可能的名稱變體 (標準化後)
                keys = {normalize_name(zh_name)}
                if en_name:
                    keys.add(normalize_name(en_name))

                # 加入手動設定的別名
                for alias, primary in alias_map.items():
                    if normalize_name(zh_name) == normalize_name(primary):
                        keys.add(normalize_name(alias))

                # 將站點 ID 加入到所有名稱變體的集合中
                for key in keys:
                    if key: # 確保名稱不為空
                        if key not in station_map:
                            station_map[key] = set()
                        station_map[key].add(station_id)

    # 將集合轉換為排序過的列表，方便儲存和讀取
    station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}

    # 確保資料夾存在
    os.makedirs(os.path.dirname(config.STATION_DATA_PATH), exist_ok=True)
    with open(config.STATION_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(station_map_list, f, ensure_ascii=False, indent=2)

    print(f"--- ✅ 站點資料庫建立成功，共 {len(station_map_list)} 個站名。 ---")
    time.sleep(1)


def build_fare_database():
    """
    從 TDX API 獲取所有站點間的票價資訊，並儲存為 JSON 檔案。
    """
    print("\n--- [2/4] 正在建立「票價資料庫」... ---")
    all_fares_data = tdx_api.get_all_fares() # 【修正】現在這個函式存在了！
    if not all_fares_data:
        print("--- ❌ 步驟 2 失敗: 無法獲取票價資料。請檢查 API 金鑰與網路。 ---")
        return

    fare_map = {}
    for info in all_fares_data:
        o_id, d_id, fares = info.get("OriginStationID"), info.get("DestinationStationID"), info.get("Fares")
        if o_id and d_id and fares:
            key = f"{o_id}-{d_id}"
            # 提取全票和兒童票價格 (注意 TDX 的 FareClass: 1=普通, 4=孩童)
            adult_fare = next((f.get("Price") for f in fares if f.get("FareClass") == 1), 0)
            child_fare = next((f.get("Price") for f in fares if f.get("FareClass") == 4), 0)
            fare_map[key] = {"全票": adult_fare, "兒童票": child_fare}

    os.makedirs(os.path.dirname(config.FARE_DATA_PATH), exist_ok=True)
    with open(config.FARE_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(fare_map, f, ensure_ascii=False, indent=2)

    print(f"--- ✅ 票價資料庫建立成功，共 {len(fare_map)} 筆票價組合。 ---")
    time.sleep(1)


def build_transfer_database():
    """
    從 TDX API 獲取捷運轉乘資訊，並儲存為 JSON 檔案。
    """
    print("\n--- [3/4] 正在建立「轉乘資料庫」... ---")
    transfer_data = tdx_api.get_line_transfer_info() # 【修正】現在這個函式存在了！
    if not transfer_data:
        print("--- ❌ 步驟 3 失敗: 無法獲取轉乘資料。 ---")
        return

    os.makedirs(os.path.dirname(config.TRANSFER_DATA_PATH), exist_ok=True)
    with open(config.TRANSFER_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(transfer_data, f, ensure_ascii=False, indent=2)

    print(f"--- ✅ 轉乘資料庫建立成功，共 {len(transfer_data)} 筆轉乘資訊。 ---")
    time.sleep(1)


def build_facilities_database():
    """
    【修改】從 TDX API 一次性獲取所有車站的設施資訊，並儲存為 JSON 檔案。
    """
    print("\n--- [4/4] 正在建立「車站設施資料庫」... ---")
    
    # 【修改】一次性獲取所有場站設施，效率更高
    all_facilities_data = tdx_api.get_station_facilities()
    if not all_facilities_data:
        print("--- ❌ 步驟 4 失敗: 無法獲取車站設施資料。 ---")
        return
        
    facilities_map = {}
    # 將相同 StationID 的設施資訊聚合在一起
    for facility in all_facilities_data:
        station_id = facility.get('StationID')
        if station_id:
            description = facility.get('FacilityDescription', '無詳細資訊').replace('\r\n', '\n')
            if station_id not in facilities_map:
                facilities_map[station_id] = []
            facilities_map[station_id].append(description)

    # 將每個站的設施描述列表合併成一個單一的、用換行符分隔的字串
    final_facilities_map = {
        station_id: "\n".join(descriptions)
        for station_id, descriptions in facilities_map.items()
    }

    os.makedirs(os.path.dirname(config.FACILITIES_DATA_PATH), exist_ok=True)
    with open(config.FACILITIES_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_facilities_map, f, ensure_ascii=False, indent=4)

    print(f"--- ✅ 車站設施資料庫已成功建立於 {config.FACILITIES_DATA_PATH}，共包含 {len(final_facilities_map)} 個站點的設施資訊。 ---")
    time.sleep(1)


if __name__ == "__main__":
    # 確保 data 資料夾存在
    if not os.path.exists('data'):
        os.makedirs('data')

    print("--- 🚀 開始建立本地資料庫 ---")

    # 依序呼叫所有資料庫建立函式
    build_station_database()
    build_fare_database()
    build_transfer_database()
    build_facilities_database()

    print("\n--- 🎉 所有本地資料庫建立完成！可以啟動主程式了。 ---")