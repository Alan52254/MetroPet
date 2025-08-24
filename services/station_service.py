# services/station_service.py
import json
import os
import re
import logging
from typing import List, Dict, Optional, Set

# --- 路徑設置 ---
import sys
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
MODEL_DIR = os.path.join(PROJECT_ROOT, 'model')

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- 延遲導入，避免循環依賴和方便測試 ---
try:
    import config
    from services.tdx_service import tdx_api
    from utils.exceptions import DataLoadError, StationNotFoundError
except ImportError as e:
    # 允許在沒有安裝完整環境的情況下，仍能被其他腳本引用或進行單元測試
    config, tdx_api, DataLoadError, StationNotFoundError = None, None, Exception, Exception
    print(f"Warning: Could not import dependencies: {e}. Running in standalone/test mode.")


# --- 配置日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ===========================================================================
# 【核心】定義精確且完整的台北捷運路網圖
# - 路線內的站點嚴格按照官方順序排列。
# - 支線和分岔路線被獨立定義，以確保方向判斷的準確性。
# ===========================================================================
LINE_NETWORKS: Dict[str, List[str]] = {
    "文湖線": [
        "動物園", "木柵", "萬芳社區", "萬芳醫院", "辛亥", "麟光", "六張犁",
        "科技大樓", "大安", "忠孝復興", "南京復興", "中山國中", "松山機場",
        "大直", "劍南路", "西湖", "港墘", "文德", "內湖", "大湖公園", "葫洲",
        "東湖", "南港軟體園區", "南港展覽館"
    ],
    "淡水信義線": [
        "象山", "台北101/世貿", "信義安和", "大安", "大安森林公園", "東門",
        "中正紀念堂", "台大醫院", "台北車站", "中山", "雙連", "民權西路",
        "圓山", "劍潭", "士林", "芝山", "明德", "石牌", "唭哩岸", "奇岩",
        "北投", "復興崗", "忠義", "關渡", "竹圍", "紅樹林", "淡水"
    ],
    "新北投支線": ["北投", "新北投"],
    "松山新店線": [
        "新店", "新店區公所", "七張", "大坪林", "景美", "萬隆", "公館", "台電大樓",
        "古亭", "中正紀念堂", "小南門", "西門", "北門", "中山", "松江南京", "南京復興",
        "台北小巨蛋", "南京三民", "松山"
    ],
    "小碧潭支線": ["七張", "小碧潭"],
    "中和新蘆線_主幹": [
        "南勢角", "景安", "永安市場", "頂溪", "古亭", "東門", "忠孝新生",
        "松江南京", "行天宮", "中山國小", "民權西路", "大橋頭"
    ],
    "中和新蘆線_迴龍": [
        "大橋頭", "台北橋", "菜寮", "三重", "先嗇宮", "頭前庄", "新莊", "輔大",
        "丹鳳", "迴龍"
    ],
    "中和新蘆線_蘆洲": [
        "大橋頭", "三重國小", "三和國中", "徐匯中學", "三民高中", "蘆洲"
    ],
    "板南線": [
        "頂埔", "永寧", "土城", "海山", "亞東醫院", "府中", "板橋", "新埔",
        "江子翠", "龍山寺", "西門", "台北車站", "善導寺", "忠孝新生", "忠孝復興",
        "忠孝敦化", "國父紀念館", "市政府", "永春", "後山埤", "昆陽", "南港", "南港展覽館"
    ],
    "環狀線": [
        "大坪林", "十四張", "秀朗橋", "景平", "景安", "中和", "橋和", "中原",
        "板新", "板橋", "新埔民生", "頭前庄", "幸福", "新北產業園區"
    ]
}

class StationManager:
    def __init__(self, station_data_path: Optional[str] = None):
        self.station_data_path = station_data_path
        self.station_aliases = self._get_station_aliases()
        self.official_name_map: Dict[str, str] = {}
        self.station_map = self._load_or_create_station_data() if station_data_path else {}

        # 【核心升級】建立標準化後的路網圖 & 車站到路線的反向索引
        self.normalized_line_networks = self._normalize_line_networks()
        self.station_to_lines_map = self._create_station_to_lines_map()
        
        self._add_aliases_to_station_map()
        logger.info("--- ✅ StationManager 初始化完成，路網知識已建立 ---")

    def _get_station_aliases(self) -> Dict[str, str]:
        """定義常用站點別名。鍵是別名，值是官方全名。"""
        aliases = {
            "北車": "台北車站", "台車": "台北車站", "101": "台北101/世貿",
            "輔大": "輔仁大學", "國父紀念館": "國父紀念館", "中正紀念堂": "中正紀念堂",
        }
        return {self._normalize_name(k): v for k, v in aliases.items()}

    def _normalize_name(self, name: str) -> str:
        """【核心修改】統一的站名標準化函式，新增移除 '往' 字的功能。"""
        if not name: return ""
        # 【新增】移除開頭的 "往" 字，並去除前後空白
        name = re.sub(r'^(往|to)\s*', '', name, flags=re.IGNORECASE).strip()
        # 移除括號內容
        name = re.sub(r'[（\(][^）\)]*[）\)]', '', name)
        # 移除結尾的 "站" 字，去除空白，轉為小寫
        return re.sub(r'站$', '', name).strip().lower()

    def _normalize_line_networks(self) -> Dict[str, List[str]]:
        """將 LINE_NETWORKS 中的所有站名標準化。"""
        return {
            line: [self._normalize_name(s) for s in stations]
            for line, stations in LINE_NETWORKS.items()
        }

    def _create_station_to_lines_map(self) -> Dict[str, List[str]]:
        """【核心升級】建立從「標準化站名」到「所屬路線列表」的反向索引地圖。"""
        s_to_l_map: Dict[str, List[str]] = {}
        for line_name, stations in self.normalized_line_networks.items():
            for station_name in stations:
                if station_name not in s_to_l_map:
                    s_to_l_map[station_name] = []
                s_to_l_map[station_name].append(line_name)
        return s_to_l_map

    # --- 資料載入與更新相關方法 (與之前大致相同) ---
    def _load_or_create_station_data(self) -> dict:
        if os.path.exists(self.station_data_path) and os.path.getsize(self.station_data_path) > 0:
            try:
                with open(self.station_data_path, 'r', encoding='utf-8') as f: data = json.load(f)
                if data:
                    logger.info(f"--- ✅ 已從本地載入站點資料 ---")
                    self._build_official_name_map_from_api_data()
                    return data
            except Exception as e: logger.warning(f"--- ⚠️ 讀取站點資料失敗 ({e})，將重新生成。 ---")
        return self.update_station_data()

    def update_station_data(self) -> dict:
        if not tdx_api: raise RuntimeError("TDX API service is not available.")
        all_stations_data = tdx_api.get_all_stations_of_route()
        if not all_stations_data: logger.error("--- ❌ 無法從 TDX API 獲取車站資料 ---"); return {}
        
        station_map, temp_official_map = {}, {}
        for route in all_stations_data:
            for station in route.get('Stations', []):
                zh_name, station_id = station.get('StationName', {}).get('Zh_tw'), station.get('StationID')
                if not (zh_name and station_id): continue
                norm_name = self._normalize_name(zh_name)
                if norm_name:
                    if norm_name not in station_map: station_map[norm_name] = set()
                    station_map[norm_name].add(station_id)
                    temp_official_map[norm_name] = zh_name
        
        station_map_list = {k: sorted(list(v)) for k, v in station_map.items()}
        os.makedirs(os.path.dirname(self.station_data_path), exist_ok=True)
        with open(self.station_data_path, 'w', encoding='utf-8') as f: json.dump(station_map_list, f, ensure_ascii=False, indent=2)
        logger.info(f"--- ✅ 站點資料已成功建立於 {self.station_data_path} ---")
        self.official_name_map = temp_official_map
        return station_map_list

    def _build_official_name_map_from_api_data(self):
        if not tdx_api: raise RuntimeError("TDX API service is not available.")
        all_stations_data = tdx_api.get_all_stations_of_route()
        if not all_stations_data: logger.warning("--- ⚠️ 無法獲取原始車站資料以建立 official_name_map ---"); return
        for route in all_stations_data:
            for station in route.get('Stations', []):
                if zh_name := station.get('StationName', {}).get('Zh_tw'):
                    self.official_name_map[self._normalize_name(zh_name)] = zh_name

    def _add_aliases_to_station_map(self):
        for alias, official_name in self.station_aliases.items():
            norm_official = self._normalize_name(official_name)
            if norm_official in self.station_map:
                self.station_map[alias] = self.station_map[norm_official]
                self.official_name_map[alias] = official_name
            else: logger.warning(f"--- ⚠️ 別名 '{alias}' 的官方名稱 '{official_name}' 不在 station_map 中 ---")

    # --- 公開查詢方法 ---
    def resolve_station_alias(self, name: str) -> str:
        """將使用者輸入（可能是別名）轉換為標準化的官方名稱。"""
        norm_input = self._normalize_name(name)
        return self._normalize_name(self.station_aliases.get(norm_input, norm_input))

    def get_station_ids(self, station_name: str) -> Optional[List[str]]:
        """根據站名（含別名）回傳對應的 Station ID 列表。"""
        resolved_key = self.resolve_station_alias(station_name)
        return self.station_map.get(resolved_key)

    def get_official_unnormalized_name(self, name: str) -> str:
        """根據標準化或別名，回傳其原始的官方全名。"""
        resolved_name = self.resolve_station_alias(name)
        return self.official_name_map.get(resolved_name, name)

    def get_terminal_stations_for(self, station_name: str) -> List[str]:
        """根據站名，回傳該站點所有路線的終點站 (標準化名稱)。"""
        resolved_name = self.resolve_station_alias(station_name)
        terminals: Set[str] = set()
        if lines := self.station_to_lines_map.get(resolved_name):
            for line_name in lines:
                stations = self.normalized_line_networks[line_name]
                terminals.add(stations[0])
                terminals.add(stations[-1])
        return sorted(list(terminals))

    def resolve_direction(self, start_station: str, direction_query: str) -> List[str]:
        """
        【核心升級】根據起始站和方向查詢，解析出正確的官方終點站名稱 (已標準化)。
        """
        norm_start = self.resolve_station_alias(start_station)
        norm_dest = self.resolve_station_alias(direction_query)

        if not direction_query or norm_dest == 'any':
            return self.get_terminal_stations_for(norm_start)

        start_lines = self.station_to_lines_map.get(norm_start, [])
        dest_lines = self.station_to_lines_map.get(norm_dest, [])
        
        # 找出起點和終點共同的路線
        common_lines = set(start_lines) & set(dest_lines)
        if not common_lines:
            logger.warning(f"--- ⚠️ '{norm_start}' 和 '{norm_dest}' 不在任何一條直達路線上。 ---")
            return []

        possible_terminals: Set[str] = set()
        for line in common_lines:
            stations = self.normalized_line_networks[line]
            try:
                start_idx = stations.index(norm_start)
                dest_idx = stations.index(norm_dest)
                
                if start_idx < dest_idx:
                    possible_terminals.add(stations[-1])  # 往列表末端方向
                elif start_idx > dest_idx:
                    possible_terminals.add(stations[0])   # 往列表開頭方向
            except ValueError:
                continue
        
        if not possible_terminals:
             logger.warning(f"--- ⚠️ 無法解析從 '{start_station}' 到 '{direction_query}' 的方向。 ---")
        
        return sorted(list(possible_terminals))

# --- 建立單一實例 (如果 config 存在) ---
station_manager = None
if config:
    station_manager = StationManager(config.STATION_DATA_PATH)

# ===========================================================================
# 【新增】內建測試程式碼
# 您可以直接執行 `python services/station_service.py` 來驗證路網邏輯
# ===========================================================================
if __name__ == '__main__':
    print("--- 正在執行 StationManager 內部測試 ---")
    
    # 在沒有 config 和 tdx_api 的情況下，進行離線測試
    # 我們只需要路網邏輯，所以傳入 None 來跳過 API 資料載入
    test_manager = StationManager(station_data_path=None)

    test_cases = [
        ("台北車站", "中山"),          # 您的案例：紅線
        ("中山", "台北車站"),          # 反向測試
        ("西門", "松山"),              # 綠線
        ("西門", "頂埔"),              # 藍線
        ("大安", "象山"),              # 紅線 (轉乘站)
        ("大安", "南港展覽館"),      # 文湖線 (轉乘站)
        ("古亭", "南勢角"),          # 橘線
        ("大橋頭", "蘆洲"),          # 橘線 (蘆洲支線)
        ("大橋頭", "迴龍"),          # 橘線 (迴龍支線)
        ("北車", "市政府"),          # 別名測試
        ("台北車站", "any"),           # 查詢所有終點站
        ("台北車站", "大安"),           # 跨線查詢 (紅線/文湖線)，應同時回傳兩個方向
    ]

    print("\n--- 測試 resolve_direction() ---")
    for start, dest in test_cases:
        result = test_manager.resolve_direction(start, dest)
        print(f"從「{start}」往「{dest}」\t=> 應行駛方向(終點站): {result}")

    print("\n--- 測試 get_terminal_stations_for() ---")
    stations_to_test = ["台北車站", "中山", "西門", "大安", "大橋頭"]
    for station in stations_to_test:
        result = test_manager.get_terminal_stations_for(station)
        print(f"「{station}」站所有可能的終點站: {result}")