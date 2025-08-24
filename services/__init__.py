#services/service_registry.py

import logging
import config
from utils.exceptions import ServiceInitializationError
from services.tdx_service import tdx_api

# --- 服務類別 Import ---
from .fare_service import FareService
from .routing_service import RoutingManager 
from .station_service import StationManager 
from .local_data_service import LocalDataManager 
from .lost_and_found_service import LostAndFoundService
from .metro_soap_service import MetroSoapService
from .prediction_service import CongestionPredictor 
from .first_last_train_time_service import FirstLastTrainTimeService 
from .realtime_mrt_service import RealtimeMRTService 
from .analysis_service import PredictionAnalysisService # <<< 1. 新增匯入我們的繪圖分析服務

# 設定日誌記錄器
logger = logging.getLogger(__name__)

class ServiceRegistry:
    """
    一個集中管理所有業務服務實例的註冊中心。
    採用單例模式，確保整個應用程式共享同一組服務實例。
    """
    _instance = None
    _is_initialized = False

    # --- 服務實例的類型提示 ---
    local_data_manager: LocalDataManager
    station_manager: StationManager
    tdx_api: tdx_api 
    metro_soap_service: MetroSoapService 
    fare_service: FareService
    routing_manager: RoutingManager
    lost_and_found_service: LostAndFoundService
    congestion_predictor: CongestionPredictor
    first_last_train_time_service: FirstLastTrainTimeService 
    realtime_mrt_service: RealtimeMRTService 
    prediction_analysis_service: PredictionAnalysisService # <<< 2. 新增類型提示

    def __new__(cls):
        if cls._instance is None:
            logger.info("Creating new ServiceRegistry instance.")
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            if not cls._is_initialized:
                cls._instance._initialize_services()
                cls._is_initialized = True
        return cls._instance

    def _initialize_services(self):
        """
        在應用啟動時，載入所有資料並初始化所有服務。
        """
        logger.info("Initializing services...")
        try:
            # 1. 初始化無依賴或基礎服務
            self.local_data_manager = LocalDataManager()
            from .station_service import station_manager as sm_instance
            self.station_manager = sm_instance 
            
            from services.tdx_service import tdx_api as tdx_api_instance
            self.tdx_api = tdx_api_instance 
            
            # 2. 初始化需要配置的服務 (如 SOAP Service)
            self.metro_soap_service = MetroSoapService(
                username=config.METRO_API_USERNAME,
                password=config.METRO_API_PASSWORD
            )

            # 3. 初始化依賴其他服務的服務
            self.fare_service = FareService(
                fare_data=self.local_data_manager.fares,
                station_id_map=self.station_manager.station_map # 更正為使用 station_manager 的 ID 對應
            )
            
            self.routing_manager = RoutingManager(
                station_manager_instance=self.station_manager,
                metro_soap_service_instance=self.metro_soap_service,
                tdx_api_instance=self.tdx_api 
            )
            
            self.lost_and_found_service = LostAndFoundService(
                metro_soap_service=self.metro_soap_service
            )

            self.congestion_predictor = CongestionPredictor(
                station_manager_instance=self.station_manager
            )
            
            # <<< 3. 在此處新增分析服務的初始化 >>>
            # 它在 congestion_predictor 之後初始化是個好習慣，因為它依賴於前者
            self.prediction_analysis_service = PredictionAnalysisService(
                station_manager=self.station_manager,
                congestion_predictor=self.congestion_predictor
            )

            # 【重點修正】初始化 FirstLastTrainTimeService
            # 將 timetable_data_path 指向 CSV 檔案路徑
            from .first_last_train_time_service import FirstLastTrainTimeService as fltt_service
            self.first_last_train_time_service = fltt_service(
                data_file_path=config.FIRST_LAST_TIMETABLE_DATA_PATH, # <--- 這裡已經修正為 CSV 路徑！
                station_manager=self.station_manager
            )

            self.realtime_mrt_service = RealtimeMRTService(
                metro_soap_api=self.metro_soap_service,
                station_manager=self.station_manager
            )
            self.realtime_mrt_service.start_update_thread() 

            logger.info("All services initialized successfully.")
        except Exception as e:
            logger.error(f"服務初始化失敗: {e}", exc_info=True)
            raise ServiceInitializationError(f"核心服務初始化失敗: {e}")

    def get_fare_service(self) -> FareService:
        return self.fare_service

    def get_routing_manager(self) -> RoutingManager:
        return self.routing_manager
    
    def get_station_manager(self) -> StationManager:
        return self.station_manager

    def get_local_data_manager(self) -> LocalDataManager:
        return self.local_data_manager

    def get_tdx_api(self): 
        return self.tdx_api

    def get_lost_and_found_service(self) -> LostAndFoundService:
        return self.lost_and_found_service

    def get_metro_soap_service(self) -> MetroSoapService:
        return self.metro_soap_service

    def get_congestion_predictor(self) -> CongestionPredictor:
        return self.congestion_predictor

    def get_first_last_train_time_service(self) -> FirstLastTrainTimeService:
        return self.first_last_train_time_service

    def get_realtime_mrt_service(self) -> RealtimeMRTService:
        return self.realtime_mrt_service

    # <<< 4. 新增 Getter 方法，讓 tools 可以取用新服務 >>>
    def get_prediction_analysis_service(self) -> PredictionAnalysisService:
        return self.prediction_analysis_service

service_registry = ServiceRegistry()