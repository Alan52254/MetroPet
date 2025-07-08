# agent/function_tools.py
import json
from langchain_core.tools import tool

# --- 導入我們所有的服務 ---
from services.station_service import station_manager
from services.routing_service import routing_manager
from services.fare_service import fare_manager
from services.exit_service import exit_manager
from services.metro_soap_service import metro_soap_api
from services.tdx_service import tdx_api

@tool
def get_mrt_fare(start_station_name: str, end_station_name: str) -> str:
    """
    當使用者查詢從 A 站到 B 站的票價時使用。
    """
    print(f"--- [工具] 從本地資料庫查詢票價: {start_station_name} -> {end_station_name} ---")
    start_id = station_manager.get_station_id(start_station_name)
    end_id = station_manager.get_station_id(end_station_name)
    if not start_id or not end_id:
        return json.dumps({"error": "找不到起點或終點站。"}, ensure_ascii=False)
    
    fare_info = fare_manager.get_fare(start_id, end_id)
    if fare_info:
        return json.dumps(fare_info, ensure_ascii=False)
    return json.dumps({"error": "找不到票價資訊。"}, ensure_ascii=False)

@tool
def plan_route(start_station_name: str, end_station_name: str) -> str:
    """
    規劃從起點到終點的最短捷運路線。
    """
    print(f"--- [工具] 規劃路線: {start_station_name} -> {end_station_name} ---")
    result = routing_manager.find_shortest_path(start_station_name, end_station_name)
    return json.dumps(result, ensure_ascii=False)

@tool
def get_station_exit_info(station_name: str) -> str:
    """
    查詢指定捷運站的出口資訊，包括出口編號及附近地標。
    """
    print(f"--- [工具] 從本地資料庫查詢車站出口: {station_name} ---")
    station_id = station_manager.get_station_id(station_name)
    if not station_id:
        return json.dumps({"error": f"找不到車站「{station_name}」。"}, ensure_ascii=False)
        
    exit_info = exit_manager.get_exits(station_id)
    if exit_info:
        return json.dumps({"station": station_name, "exits": exit_info}, ensure_ascii=False)
    return json.dumps({"error": f"找不到車站「{station_name}」的出口資訊。"}, ensure_ascii=False)

@tool
def get_first_last_train_time(station_name: str) -> str:
    """
    【已恢復】查詢指定捷運站點，各個方向（終點站）的首班車與末班車時間。
    """
    print(f"--- [工具] 查詢首末班車時間: {station_name} ---")
    station_id = station_manager.get_station_id(station_name)
    if not station_id:
        return json.dumps({"error": f"找不到車站: {station_name}"}, ensure_ascii=False)
    
    timetable_data = tdx_api.get_first_last_timetable(station_id)
    
    if timetable_data:
        timetables = []
        for item in timetable_data:
            timetables.append({
                "direction": item.get("TripHeadSign", "未知方向"),
                "first_train": item.get("FirstTrainTime", "N/A"),
                "last_train": item.get("LastTrainTime", "N/A")
            })
        return json.dumps({"station": station_name, "timetable": timetables}, ensure_ascii=False)
    
    return json.dumps({"error": f"查無 '{station_name}' 的首末班車資訊"}, ensure_ascii=False)

@tool
def get_lost_and_found_info(item_keyword: str) -> str:
    """
    【新功能】根據物品關鍵字，查詢最近在捷運拾獲的物品列表。
    """
    print(f"--- [工具] 正在從 SOAP API 查詢遺失物: {item_keyword} ---")
    all_items = metro_soap_api.get_all_lost_items()
    if all_items is None:
        return json.dumps({"error": "無法從台北捷運伺服器獲取遺失物資料。"}, ensure_ascii=False)

    found_items = [item for item in all_items if item_keyword.lower() in item.get('name', '').lower()]
    if not found_items:
        return json.dumps({"message": f"沒有找到與「{item_keyword}」相關的遺失物。"}, ensure_ascii=False)
        
    return json.dumps({"items": found_items[:5]}, ensure_ascii=False, indent=2)

# --- 【核心修正】恢復並整合所有工具的最終列表 ---
all_tools = [
    get_mrt_fare,
    plan_route,
    get_station_exit_info,
    get_first_last_train_time,
    get_lost_and_found_info,
]