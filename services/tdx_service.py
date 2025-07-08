# services/tdx_service.py
import requests
import config

class TDXApi:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://tdx.transportdata.tw/api/basic"
        self.auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        self.access_token = None

    def _get_access_token(self):
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        data = {'grant_type': 'client_credentials', 'client_id': self.client_id, 'client_secret': self.client_secret}
        try:
            response = requests.post(self.auth_url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            print("--- ✅ 成功獲取 TDX Access Token！ ---")
            self.access_token = response.json().get('access_token')
        except requests.RequestException as e:
            print(f"--- ❌ 獲取 Access Token 失敗: {e} ---")
            self.access_token = None
            
    def _get_api_data(self, url: str):
        if not self.access_token:
            self._get_access_token()
            if not self.access_token: return None
        
        headers = {'authorization': f'Bearer {self.access_token}'}
        try:
            response = requests.get(url, headers=headers, timeout=20) # 延長超時時間
            if response.status_code == 401:
                print("--- ⚠️ Access Token 已過期，正在重新獲取... ---")
                self._get_access_token()
                if not self.access_token: return None
                headers['authorization'] = f'Bearer {self.access_token}'
                response = requests.get(url, headers=headers, timeout=20)
            
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"--- ❌ API 請求失敗 (URL: {url}) ---")
            print(f"--- 錯誤詳情: {e} ---")
            return None

    # --- 【核心修改】加入你找到的、最高效的 API 端點 ---
    def get_all_stations_of_route(self):
        """
        【新】一次性獲取所有路線的所有車站基本資料。
        這是建立我們站點資料庫(快取)最關鍵的函式。
        """
        url = f"{self.base_url}/v2/Rail/Metro/StationOfRoute/TRTC?$format=JSON"
        return self._get_api_data(url)

    def get_mrt_fare(self, start_id: str, end_id: str):
        """查詢票價"""
        url = f"{self.base_url}/v2/Rail/Metro/ODFare/TRTC/{start_id}/to/{end_id}?$format=JSON"
        return self._get_api_data(url)

    # 其他你未來可能會用到的函式...
    def get_first_last_timetable(self, station_id: str):
        """查詢指定車站的首末班車時間"""
        url = f"{self.base_url}/v2/Rail/Metro/FirstLastTimetable/TRTC?$filter=StationID eq '{station_id}'&$format=JSON"
        return self._get_api_data(url)
    def get_station_facilities(self):
        """獲取所有台北捷運車站的設施資訊。"""
        api_url = f"{self.base_url}/v2/Metro/StationFacility/TRTC"
        return self._make_request(api_url)
    # 在 TDXApi class 中新增
    def get_station_exit_info(self):
        """一次性獲取所有車站的出口資訊。"""
        api_url = f"{self.base_url}/v2/Metro/StationExit/TRTC"
        return self._make_request(api_url)
tdx_api = TDXApi(client_id=config.TDX_CLIENT_ID, client_secret=config.TDX_CLIENT_SECRET)