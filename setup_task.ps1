$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"d:\编程练习\stock_analyzer\daily_run.vbs`""
$trigger = New-ScheduledTaskTrigger -Daily -At "4:00PM"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
Register-ScheduledTask -TaskName "StockDailyReport" -Action $action -Trigger $trigger -Settings $settings -Force -Description "每日16:00静默生成股票分析日报"
Write-Host "✅ 已设置每天16:00静默运行（不弹窗）"
