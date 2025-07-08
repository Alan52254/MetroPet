# services/local_data_service.py
import json
import config
from .station_service import station_manager

class LocalDataManager:
    def __init__(self):
        self.fares = self._load_json(config.FARE_DATA_PATH)
        print(f"--- ✅ [LocalData] 票價資料庫已載入，共 {len(self.fares)} 筆。 ---")
    
    def _load_json(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"--- ❌ [LocalData] 警告：找不到資料檔案 {path}。相關功能可能無法使用。 ---")
            return {}
        except json.JSONDecodeError:
            print(f"--- ❌ [LocalData] 警告：解析 JSON 檔案 {path} 失敗。 ---")
            return {}

    def get_fare(self, start_station_name: str, end_station_name: str) -> dict | None:
        """
        從本地快取檔案查詢票價。
        """
        start_id = station_manager.get_station_id(start_station_name)
        end_id = station_manager.get_station_id(end_station_name)

        if not start_id or not end_id:
            return None
            
        # 嘗試直接查詢，如果沒有再試著反過來查 (例如 BL01-BL05 vs BL05-BL01)
        key1 = f"{start_id}-{end_id}"
        key2 = f"{end_id}-{start_id}"

        fare_data = self.fares.get(key1) or self.fares.get(key2)
        
        if fare_data:
            return {
                "start_station": start_station_name,
                "end_station": end_station_name,
                "fares": fare_data
            }
        return None

# 建立 LocalDataManager 的單一實例
local_data_manager = LocalDataManager()