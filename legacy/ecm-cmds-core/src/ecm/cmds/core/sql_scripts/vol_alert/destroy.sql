USE [LO25]
GO

IF EXISTS (SELECT * FROM information_schema.tables WHERE table_schema='intraday_vol' AND table_name='ticker_config')
    ALTER TABLE intraday_vol.ticker_config SET (SYSTEM_VERSIONING = OFF);
GO
DROP TABLE IF EXISTS intraday_vol.ticker_config;
GO
DROP TABLE IF EXISTS intraday_vol.ticker_config_history;
GO

IF EXISTS (SELECT * FROM information_schema.tables WHERE table_schema='intraday_vol' AND table_name='watchlist')
    ALTER TABLE intraday_vol.watchlist SET (SYSTEM_VERSIONING = OFF);
GO
DROP TABLE IF EXISTS intraday_vol.watchlist;
GO
DROP TABLE IF EXISTS intraday_vol.watchlist_history;
GO

DROP SCHEMA IF EXISTS intraday_vol;
GO

