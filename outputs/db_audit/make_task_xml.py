# -*- coding: utf-8 -*-
XML = '''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Date>2026-10-08T14:05:00</Date>
    <Author>CHINAMI-4BJQV1T\\Administrator</Author>
    <Description>每周一 00:00 检查 commodity_department 库的缺失数据，生成 Markdown 报告到桌面（只读检查）。</Description>
    <URI>\\HedeDatabaseMissingDataReview</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-2375117697-1115425842-3879617283-500</UserId>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <IdleSettings>
      <Duration>PT10M</Duration>
      <WaitTimeout>PT1H</WaitTimeout>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
  </Settings>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-10-12T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <WeeksInterval>1</WeeksInterval>
        <DaysOfWeek>
          <Monday />
        </DaysOfWeek>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>E:\\hede\\backend\\scripts\\review_missing_data.cmd</Command>
    </Exec>
  </Actions>
</Task>
'''
path = r"E:\hede\outputs\db_audit\missing_data_task.xml"
open(path, "w", encoding="utf-16").write(XML)
print("written", path)
