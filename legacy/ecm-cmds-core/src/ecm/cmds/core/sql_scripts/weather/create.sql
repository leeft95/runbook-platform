USE [LO25]
GO


CREATE TABLE [dbo].[OpenMeteo_Station_Daily](
    [date] [date] NOT NULL,
    [station] [nvarchar](10) NOT NULL,
    [precip] [float] NULL,
    [tmp2m] [float] NULL,
    [dpt2m] [float] NULL
);
GO

