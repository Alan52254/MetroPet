# services/routing_service.py
import json
import os
import networkx as nx
import config
import re
from .station_service import station_manager
# 【修正】這裡我們需要 tdx_api 來獲取最原始的路網結構
from .tdx_service import tdx_api

class RoutingManager:
    def __init__(self):
        print("--- [Routing Service] 正在初始化並建立捷運路網圖... ---")
        self.station_id_to_name = self._load_station_id_map()
        self.graph = self._build_metro_graph()

    def _load_station_id_map(self) -> dict:
        """從 station_manager 建立 ID -> 名稱的對照表"""
        id_to_name = {}
        # 確保 station_map 是字典
        if not isinstance(station_manager.station_map, dict):
            print("--- ❌ [Routing] station_manager.station_map 不是一個有效的字典。---")
            return {}
            
        for name, ids in station_manager.station_map.items():
            # 我們只用中文名來建立反向地圖，排除英文名
            if not re.search('[a-zA-Z]', name):
                for station_id in ids:
                    id_to_name[station_id] = name
        return id_to_name

    def _get_line_name(self, line_id: str) -> str:
        """根據路線ID獲取中文路線名稱"""
        line_map = {
            'BL': '板南線', 'BR': '文湖線', 'R': '淡水信義線',
            'G': '松山新店線', 'O': '中和新蘆線', 'Y': '環狀線'
        }
        # 處理特殊路線代碼，例如 'G03A' (小碧潭支線)
        if len(line_id) > 2 and line_id[:2] in line_map:
            return line_map.get(line_id[:2])
        return line_map.get(line_id, '未知路線')


    def _build_metro_graph(self) -> nx.Graph:
        """
        從 TDX API 的原始資料和本地轉乘資料，建立一個帶有權重（時間）的捷運路網圖。
        權重代表從一個節點到另一個節點所需的分鐘數。
        """
        G = nx.Graph()

        # 1. 加入所有車站節點 (Node)
        # 節點是唯一的 StationID，例如 'BL01'
        for station_id, station_name in self.station_id_to_name.items():
            G.add_node(station_id, name=station_name)

        # 2. 加入相鄰車站之間的邊 (Edge)，權重為 3 分鐘
        # 這是我們的基礎路網，假設站間平均行駛時間為 3 分鐘
        all_stations_raw_data = tdx_api.get_all_stations_of_route()
        if not all_stations_raw_data:
            print("--- ❌ [Routing] 無法建立路網圖：從 TDX 獲取車站資料失敗。 ---")
            return G
            
        for route in all_stations_raw_data:
            stations_in_route = route.get("Stations", [])
            for i in range(len(stations_in_route) - 1):
                u = stations_in_route[i]['StationID']
                v = stations_in_route[i+1]['StationID']
                G.add_edge(u, v, weight=3, type='ride') # 權重暫定3分鐘

        # 3. 讀取轉乘資訊，加入轉乘的邊，權重為轉乘時間
        # 這是讓路線規劃變聰明的關鍵！
        try:
            with open(config.TRANSFER_DATA_PATH, 'r', encoding='utf-8') as f:
                transfer_data = json.load(f)
            
            for transfer in transfer_data:
                u = transfer['FromStationID']
                v = transfer['ToStationID']
                # 將秒轉換為分鐘，並加上一些緩衝
                transfer_time = max(1, round(transfer.get('TransferTime', 300) / 60))
                # 如果圖中已有這條邊(可能在不同方向重複)，更新為較短的轉乘時間
                if G.has_edge(u, v):
                    G[u][v]['weight'] = min(G[u][v]['weight'], transfer_time)
                else:
                    G.add_edge(u, v, weight=transfer_time, type='transfer')

        except FileNotFoundError:
            print(f"--- ⚠️ [Routing] 找不到轉乘資訊檔案: {config.TRANSFER_DATA_PATH} ---")
        except Exception as e:
            print(f"--- ❌ [Routing] 讀取或處理轉乘資訊時發生錯誤: {e} ---")

        print("--- ✅ [Routing] 智慧捷運路網圖建立完成！ ---")
        return G

    def find_shortest_path(self, start_name: str, end_name: str):
        """
        使用 Dijkstra 演算法尋找最短路徑（基於時間權重）。
        回傳的結果會更詳細，包含路徑、總時間、轉乘資訊。
        """
        start_ids = station_manager.station_map.get(station_manager._normalize_string(start_name))
        end_ids = station_manager.station_map.get(station_manager._normalize_string(end_name))

        if not start_ids:
            return {"error": f"找不到起點站「{start_name}」"}
        if not end_ids:
            return {"error": f"找不到終點站「{end_name}」"}

        shortest_path = None
        min_duration = float('inf')

        # 因為一個站名可能對應多個ID（如轉乘站），我們需要遍歷所有可能性
        for start_id in start_ids:
            for end_id in end_ids:
                try:
                    # 使用 networkx 的 dijkstra_path 找到節點路徑和總時間
                    path_ids = nx.dijkstra_path(self.graph, source=start_id, target=end_id, weight='weight')
                    duration = nx.dijkstra_path_length(self.graph, source=start_id, target=end_id, weight='weight')
                    
                    if duration < min_duration:
                        min_duration = duration
                        shortest_path = path_ids

                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue # 如果這對ID沒有路徑，就試下一個組合

        if not shortest_path:
            return {"error": "在路網圖中找不到從起點到終點的路徑。"}

        # --- [✨ 新增] 解析路徑，提供詳細的搭乘指南 ---
        path_details = []
        current_line = self._get_line_name(shortest_path[0][:2])
        line_start_station = self.station_id_to_name.get(shortest_path[0])
        
        for i in range(len(shortest_path) - 1):
            u, v = shortest_path[i], shortest_path[i+1]
            edge_data = self.graph.get_edge_data(u, v)

            if edge_data.get('type') == 'transfer' or current_line != self._get_line_name(v[:2]):
                # 記錄前一段搭乘
                path_details.append(f"搭乘【{current_line}】從 {line_start_station} 到 {self.station_id_to_name.get(u)}。")
                # 記錄轉乘
                next_line = self._get_line_name(v[:2])
                path_details.append(f"在 {self.station_id_to_name.get(u)} 站內轉乘【{next_line}】(估計步行 {edge_data.get('weight', 1)} 分鐘)。")
                current_line = next_line
                line_start_station = self.station_id_to_name.get(v)

        # 加上最後一段路程
        path_details.append(f"搭乘【{current_line}】從 {line_start_station} 到 {self.station_id_to_name.get(shortest_path[-1])}。")
        
        return {
            "start_station": start_name,
            "end_station": end_name,
            "path_description": "\n".join(path_details),
            "estimated_time_minutes": round(min_duration),
            "stops": len(shortest_path) - 1 - len([d for d in path_details if '轉乘' in d]) # 減去轉乘次數
        }

# 建立 RoutingManager 的單一實例
routing_manager = RoutingManager()