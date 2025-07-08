# services/metro_soap_service.py
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import config

class MetroSoapApi:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.api_url = "http://api.metro.taipei/metroapi/LoseThingForWeb.asmx"
        self.headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': '"http://tempuri.org/getLoseThingForWeb_ALL"'
        }

    def get_all_lost_items(self) -> list[dict] | None:
        """
        呼叫台北捷運的 SOAP API，獲取所有遺失物資料。
        """
        if not self.username or not self.password:
            print("--- ❌ 錯誤：缺少台北捷運 API 的帳號或密碼。 ---")
            return None

        # 組合 SOAP 的 XML 請求內容
        body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getLoseThingForWeb_ALL xmlns="http://tempuri.org/">
      <userName>{self.username}</userName>
      <passWord>{self.password}</passWord>
    </getLoseThingForWeb_ALL>
  </soap:Body>
</soap:Envelope>"""

        try:
            print("--- [SOAP] 正在呼叫遺失物 API... ---")
            response = requests.post(self.api_url, data=body.encode('utf-8'), headers=self.headers, timeout=60)
            response.raise_for_status()
            
            # --- 解析 XML 回應 ---
            # 使用 BeautifulSoup 來解析複雜的 XML 字串
            soup = BeautifulSoup(response.content, 'xml')
            
            # 找到包含所有遺失物資料的 Table 標籤
            lost_things_table = soup.find('getLoseThingForWeb_ALLResult')
            if not lost_things_table:
                print("--- ⚠️ 警告：API 回應中找不到 getLoseThingForWeb_ALLResult 標籤。 ---")
                # 檢查是否有錯誤訊息
                fault = soup.find('faultstring')
                if fault:
                    print(f"--- ❌ API 錯誤: {fault.text} ---")
                return None

            items = []
            # 遍歷每一筆遺失物 (Table 標籤)
            for thing in lost_things_table.find_all('Table'):
                item = {
                    "id": thing.find('ls_no').text if thing.find('ls_no') else '',
                    "date": thing.find('get_date').text if thing.find('get_date') else '',
                    "location": thing.find('get_place').text if thing.find('get_place') else '',
                    "name": thing.find('ls_name').text if thing.find('ls_name') else '',
                    "description": thing.find('ls_spec').text if thing.find('ls_spec') else ''
                }
                items.append(item)
            
            print(f"--- ✅ [SOAP] 成功獲取並解析了 {len(items)} 筆遺失物資料。 ---")
            return items

        except requests.RequestException as e:
            print(f"--- ❌ 呼叫 SOAP API 時發生錯誤: {e} ---")
            return None

# 建立 MetroSoapApi 的單一實例
metro_soap_api = MetroSoapApi(username=config.METRO_API_USERNAME, password=config.METRO_API_PASSWORD)