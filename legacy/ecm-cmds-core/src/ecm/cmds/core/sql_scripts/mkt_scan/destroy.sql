use lo25
go

if exists (select * from information_schema.TABLES where table_schema='mkt_scan' and table_name='ticker_config')
alter table mkt_scan.ticker_config set (system_versioning = off)
go
drop table if exists mkt_scan.ticker_config
go
drop table if exists mkt_scan.ticker_config_history
go

if exists (select * from information_schema.TABLES where table_schema='mkt_scan' and table_name='watchlist')
alter table mkt_scan.watchlist set (system_versioning = off)
go
drop table if exists mkt_scan.watchlist
go
drop table if exists mkt_scan.watchlist_history
go

drop schema if exists mkt_scan
go


if exists (select * from information_schema.TABLES where table_schema='dbo' and table_name='report_schedule')
alter table dbo.report_schedule set (system_versioning = off)
go
drop table if exists dbo.report_schedule
go
drop table if exists dbo.report_schedule_history
go
