use lo25
go

if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='jodi_gas')
alter table dbo.jodi_gas set (system_versioning = off)
go
drop table if exists dbo.jodi_gas
go
drop table if exists dbo.jodi_gas_history
go

if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='Kpler_MonthlyFlow_Load_Arrival')
alter table dbo.Kpler_MonthlyFlow_Load_Arrival set (system_versioning = off)
go
drop table if exists dbo.Kpler_MonthlyFlow_Load_Arrival
go
drop table if exists dbo.Kpler_MonthlyFlow_Load_Arrival_history
go

if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='Kpler_MonthlyFlow_Load')
alter table dbo.Kpler_MonthlyFlow_Load set (system_versioning = off)
go
drop table if exists dbo.Kpler_MonthlyFlow_Load
go
drop table if exists dbo.Kpler_MonthlyFlow_Load_history
go

if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='Kpler_MonthlyFlow_Arrival')
alter table dbo.Kpler_MonthlyFlow_Arrival set (system_versioning = off)
go
drop table if exists dbo.Kpler_MonthlyFlow_Arrival
go
drop table if exists dbo.Kpler_MonthlyFlow_Arrival_history
go

if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='Kpler_Flows_Raw')
alter table dbo.Kpler_Flows_Raw set (system_versioning = off)
go
drop table if exists dbo.Kpler_Flows_Raw
go
drop table if exists dbo.Kpler_Flows_Raw_history
go
