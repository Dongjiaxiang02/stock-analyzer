' 静默运行股票分析（不弹黑窗）
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw ""d:\编程练习\stock_analyzer\main.py""", 0, False
