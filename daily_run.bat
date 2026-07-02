@echo off
chcp 65001 >nul
cd /d d:\编程练习\stock_analyzer
echo [%date% %time%] 股票分析日报开始...
python main.py
echo [%date% %time%] 完成
