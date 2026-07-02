$action = New-ScheduledTaskAction -Execute "d:\编程练习\stock_analyzer\daily_run.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At "4:00PM"
Register-ScheduledTask -TaskName "StockDailyReport" -Action $action -Trigger $trigger -Force -Description "每日16:00自动生成股票分析日报"
Write-Host "✅ 已设置每天16:00自动生成报告"
