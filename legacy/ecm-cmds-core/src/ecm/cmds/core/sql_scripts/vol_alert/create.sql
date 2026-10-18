USE [LO25]
GO


create schema intraday_vol
GO

CREATE TABLE [intraday_vol].[ticker_config](
    [id] INT NOT NULL IDENTITY PRIMARY KEY CLUSTERED,
    [uid] NVARCHAR(MAX),
    [generic_ticker] NVARCHAR(MAX) NULL,
    [asset_class] NVARCHAR(50) NULL,
    [hidden_hours] NVARCHAR(20) NULL,
    [enabled] BIT NULL,
    [t0] datetime2 GENERATED ALWAYS AS ROW START,
    [t1] datetime2 GENERATED ALWAYS AS ROW END,
    PERIOD FOR SYSTEM_TIME ([t0],[t1])
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = intraday_vol.[ticker_config_history]));
GO

CREATE TABLE [intraday_vol].[watchlist](
    [id] INT NOT NULL IDENTITY PRIMARY KEY CLUSTERED,
    [uid] NVARCHAR(MAX),
    [generic_ticker] NVARCHAR(MAX) NULL,
    [asset_class] NVARCHAR(50) NULL,
    [ticker] NVARCHAR(MAX),
    [last_contract] NVARCHAR(MAX) NULL,
    [roll_date] DATETIME2 NULL,
    [enabled] BIT NULL,
    [update_time] DATETIME2 NULL,
    [t0] datetime2 GENERATED ALWAYS AS ROW START,
    [t1] datetime2 GENERATED ALWAYS AS ROW END,
    PERIOD FOR SYSTEM_TIME ([t0],[t1])
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = intraday_vol.[watchlist_history]));
GO

