USE [LO25]
GO


create schema mkt_scan
go

CREATE TABLE [mkt_scan].[ticker_config](
    [id] int not null identity primary key clustered,
    [uid] [nvarchar](max),
    [generic_ticker] [nvarchar](max) NULL,
    [asset_class] [nvarchar](50) NULL,
    [category] [nvarchar](50) NULL,
    [change_type] [nvarchar](50) NULL,
    [volume] [bit] NULL,
    [enabled] [bit] NULL,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = mkt_scan.[ticker_config_history]))
go


CREATE TABLE [mkt_scan].[watchlist](
    [id] int not null identity primary key clustered,
    [uid] [nvarchar](max),
    [generic_ticker] [nvarchar](max) NULL,
    [asset_class] [nvarchar](50) NULL,
    [category] [nvarchar](50) NULL,
    [change_type] [nvarchar](50) NULL,
    [ticker] [nvarchar](max),
    [volume] [bit] NULL,
    [enabled] [bit] NULL,
    [update_time] [datetime2],
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = mkt_scan.[watchlist_history]))
go

CREATE TABLE [dbo].[report_schedule](
    [id] int not null identity primary key clustered,
    [report_name] [nvarchar](max) not NULL,
    [market] [nvarchar](max) not NULL,
    [enabled] [bit] NULL,
    [schedule_time] [datetime2] not NULL,
    [timezone] [nvarchar](max) not NULL,
    [repeat_duration] time NULL,
    [repeat_interval] time NULL,
    [schedule_days] int not NULL,
    [report_path] [nvarchar](max) not NULL,
    [python_executable] [nvarchar](max) not NULL,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[report_schedule_history]))
go
