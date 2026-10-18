CREATE SCHEMA alerts
GO

CREATE TABLE [alerts].[config](
    [id] INT NOT NULL IDENTITY PRIMARY KEY CLUSTERED,
    [uid] NVARCHAR(MAX) NOT NULL,
    [alert_type] NVARCHAR(100) NOT NULL,
    [product] NVARCHAR(100) NOT NULL,
    [alert_func] NVARCHAR(MAX) NOT NULL,
    [description] NVARCHAR(MAX) NULL,
    [threshold] FLOAT NULL,
    [operator] NVARCHAR(MAX) NULL,
    [enabled] BIT NULL,
    [alert_params] NVARCHAR(MAX) NULL,
    [alert_time_utc] DATETIME2 NULL,
    [alert_time_name] NVARCHAR(MAX) NULL,
    [t0] DATETIME2 GENERATED ALWAYS AS ROW START,
    [t1] DATETIME2 GENERATED ALWAYS AS ROW END,
    PERIOD FOR SYSTEM_TIME ([t0], [t1])
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = alerts.[config_history]))
GO

CREATE TABLE [alerts].[live](
    [id] INT NOT NULL IDENTITY PRIMARY KEY CLUSTERED,
    [uid] [nvarchar](max) NOT NULL,
    [alert_type] [nvarchar](100) NOT NULL,
    [product] [nvarchar](100) NOT NULL,
    [alert_func] [nvarchar](max) NOT NULL,
    [description] [nvarchar](max) NULL,
    [threshold] [float] NULL,
    [alert_time] [datetime2](7) NOT NULL,
    [alert_value] [float] NULL,
    [alert_params] [nvarchar](max) NULL,
    [meta] [nvarchar](max) NULL,
    [approval_state] [int] NOT NULL,
    [approved_by] [nvarchar](max) NULL,
    [approval_time] [datetime2] NULL,
    [t0] DATETIME2 GENERATED ALWAYS AS ROW START,
    [t1] DATETIME2 GENERATED ALWAYS AS ROW END,
    PERIOD FOR SYSTEM_TIME ([t0], [t1])
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = alerts.[live_history]))
GO

CREATE TABLE [alerts].[alert_type](
    [id] INT NOT NULL IDENTITY PRIMARY KEY CLUSTERED,
    [alert_type] NVARCHAR(MAX) NOT NULL,
    [description] NVARCHAR(MAX) NULL,
    [t0] DATETIME2 GENERATED ALWAYS AS ROW START,
    [t1] DATETIME2 GENERATED ALWAYS AS ROW END,
    PERIOD FOR SYSTEM_TIME ([t0], [t1])
) with (SYSTEM_VERSIONING = ON (HISTORY_TABLE = alerts.[alert_type_history]))
GO
