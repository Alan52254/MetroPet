import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

# --- 依賴其他的服務 ---
from .station_service import StationManager
from .prediction_service import CongestionPredictor

# --- 路徑設定 ---
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)

logger = logging.getLogger(__name__)

class PredictionAnalysisService:
    def __init__(self, station_manager: StationManager, congestion_predictor: CongestionPredictor):
        """
        初始化分析服務，它需要 StationManager 和 CongestionPredictor 才能運作。
        """
        self.station_manager = station_manager
        self.congestion_predictor = congestion_predictor
        self.plots_dir = os.path.join(PROJECT_ROOT, 'plots')
        os.makedirs(self.plots_dir, exist_ok=True)
        logger.info("--- ✅ PredictionAnalysisService 初始化完成 ---")

    def get_daily_congestion_dataframe(self, station_name: str, direction: str, target_date: date) -> Optional[pd.DataFrame]:
        """
        【核心邏輯】為指定站點、方向和日期，生成一整天的每小時平均擁擠度預測數據。
        
        這裡包含了更聰明的方向處理邏輯。
        """
        # --- 1. 智慧方向解析 ---
        official_station_name = self.station_manager.get_official_unnormalized_name(station_name)
        
        # 取得該站所有可能的終點站
        possible_terminals = self.station_manager.get_terminal_stations_for(station_name)
        
        # 如果是終點站，只有一個行駛方向
        if len(possible_terminals) == 1:
            target_terminal_key = possible_terminals[0]
            logger.info(f"偵測到終點站 '{official_station_name}'，自動設定方向為唯一的終點站 '{target_terminal_key}'")
        else:
            # 對於非終點站，使用 resolve_direction 解析
            final_terminal_keys = self.station_manager.resolve_direction(official_station_name, direction)
            if not final_terminal_keys:
                logger.warning(f"無法從 '{official_station_name}' 解析往 '{direction}' 的方向。")
                return None
            target_terminal_key = final_terminal_keys[0]

        target_terminal_for_prediction = self.station_manager.get_official_unnormalized_name(target_terminal_key)
        logger.info(f"--- 方向解析成功: 使用者輸入 '{direction}' -> 模型輸入 '{target_terminal_for_prediction}' ---")

        # --- 2. 數據生成與聚合 ---
        hourly_predictions = []
        for hour in range(24):
            target_datetime = datetime.combine(target_date, datetime.min.time()).replace(hour=hour)
            
            prediction_result = self.congestion_predictor.predict_for_station(
                station_name=official_station_name,
                direction=target_terminal_for_prediction,
                target_datetime=target_datetime
            )
            
            if "error" not in prediction_result and prediction_result.get("congestion_by_car"):
                car_levels = [car['congestion_level'] for car in prediction_result["congestion_by_car"]]
                average_congestion = np.mean(car_levels) if car_levels else 0
                hourly_predictions.append({
                    'hour': hour,
                    'average_congestion_level': average_congestion
                })
        
        if not hourly_predictions:
            return None

        return pd.DataFrame(hourly_predictions)

    def plot_daily_congestion(self, daily_df: pd.DataFrame, station_name: str, direction: str, target_date: date) -> str:
        """
        接收一個 DataFrame，並將其繪製成每日擁擠度圖表。
        """
        congestion_map_text = {1: "舒適", 2: "正常", 3: "略多", 4: "擁擠"}
        
        plt.style.use('seaborn-v0_8-whitegrid')
        fig, ax = plt.subplots(figsize=(16, 8))
        
        ax.bar(
            daily_df['hour'],
            daily_df['average_congestion_level'],
            color='#1f77b4',
            width=0.8,
            alpha=0.8,
            edgecolor='black'
        )
        
        # 設定中文字體，請確保你的環境有支援的字體，例如 'Microsoft JhengHei'
        plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
        plt.rcParams['axes.unicode_minus'] = False # 解決負號顯示問題

        ax.set_title(
            f'{station_name} 往 {direction} 方向之每小時擁擠度預測\n日期: {target_date.strftime("%Y-%m-%d")}',
            fontsize=18, color='darkred', pad=20
        )
        ax.set_xlabel('時間 (小時)', fontsize=14, color='darkgreen')
        ax.set_ylabel('平均擁擠度等級', fontsize=14, color='darkgreen')
        ax.set_xticks(range(24))
        ax.tick_params(axis='x', labelsize=10)
        
        # 設置 Y 軸刻度為中文擁擠度描述
        ax.set_yticks(list(congestion_map_text.keys()))
        ax.set_yticklabels(list(congestion_map_text.values()), fontsize=10)
        ax.set_ylim(bottom=0.5, top=4.5) # 讓Y軸範圍更清晰

        ax.axvspan(6.5, 9.5, color='red', alpha=0.1, label='上午尖峰')
        ax.axvspan(16.5, 19.5, color='orange', alpha=0.1, label='下午尖峰')
        
        ax.legend(fontsize=12, loc='upper left')
        fig.tight_layout()
        
        # 將圖片儲存到檔案
        filename = f'congestion_chart_{station_name}_{direction}_{target_date.strftime("%Y%m%d")}.png'
        save_path = os.path.join(self.plots_dir, filename)
        fig.savefig(save_path, dpi=300)
        plt.close(fig)
        
        logger.info(f"✅ 擁擠度圖表已成功儲存至: {save_path}")
        return save_path