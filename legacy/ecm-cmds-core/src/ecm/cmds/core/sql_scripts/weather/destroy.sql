USE [LO25]
GO

IF EXISTS (SELECT * FROM information_schema.tables WHERE table_schema='dbo' AND table_name='OpenMeteo_Station_Daily')
DROP TABLE IF EXISTS dbo.OpenMeteo_Station_Daily;
GO
