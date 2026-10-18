USE LO25


CREATE TABLE [dbo].[jodi_gas](
    [id] int not null identity primary key clustered,
    [TIME_PERIOD] [datetime2] not null,
    [REF_AREA] [nvarchar](100) not null,
    [ENERGY_PRODUCT] [nvarchar](max) not null,
    [FLOW_BREAKDOWN] [nvarchar](max) not null,
    [UNIT_MEASURE] [nvarchar](max) not null,
    [OBS_VALUE] [float] null,
    [ASSESSMENT_CODE] [int] null,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[jodi_gas_history]))
GO


CREATE TABLE [dbo].[Kpler_MonthlyFlow_Load_Arrival]
(
    [id] int not null identity primary key clustered,
    [start_month_year] [date] not null,
    [origin_country_name] [nvarchar](100) not null,
    [destination_country_name] [nvarchar](100) not null,
    [cargo_origin_cubic_meters] [float] null,
    [cargo_destination_cubic_meters] [float] null,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[Kpler_MonthlyFlow_Load_Arrival_history]))
GO

CREATE TABLE [dbo].[Kpler_MonthlyFlow_Load]
(
    [id] int not null identity primary key clustered,
    [start_month_year] [date] not null,
    [origin_country_name] [nvarchar](100) not null,
    [destination_country_name] [nvarchar](100) not null,
    [cargo_origin_cubic_meters] [float] null,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[Kpler_MonthlyFlow_Load_history]))

CREATE TABLE [dbo].[Kpler_MonthlyFlow_Arrival]
(
    [id] int not null identity primary key clustered,
    [end_month_year] [date] not null,
    [origin_country_name] [nvarchar](100) not null,
    [destination_country_name] [nvarchar](100) not null,
    [cargo_destination_cubic_meters] [float] null,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[Kpler_MonthlyFlow_Arrival_history]))

CREATE TABLE [dbo].[Kpler_Flows_Raw]
(
    [id] [int] IDENTITY(1,1) NOT NULL,
    [last_update] [datetime2](7) NOT NULL,
    [vessel_name] [nvarchar](max) NULL,
    [start_date] [datetime2](7) NULL,
    [origin_location_name] [nvarchar](max) NULL,
    [origin_eta_source] [nvarchar](max) NULL,
    [cargo_origin_cubic_meters] [int] NULL,
    [origin_reload_sts_partial] [nvarchar](max) NULL,
    [end_date] [datetime2](7) NULL,
    [destination_location_name] [nvarchar](max) NULL,
    [destination_eta_source] [nvarchar](max) NULL,
    [cargo_destination_cubic_meters] [int] NULL,
    [destination_reload_sts_partial] [nvarchar](max) NULL,
    [next_forecasted_destination_location_name] [nvarchar](max) NULL,
    [next_forecasted_destination_location_eta] [datetime2](7) NULL,
    [next_forecasted_destination_confidence] [float] NULL,
    [export_price] [float] NULL,
    [export_number_of_trades] [float] NULL,
    [import_price] [float] NULL,
    [import_number_of_trades] [float] NULL,
    [status] [nvarchar](max) NULL,
    [initial_seller_name] [nvarchar](max) NULL,
    [final_buyer_name] [nvarchar](max) NULL,
    [number_of_intermediaries] [float] NULL,
    [origin_country_name] [nvarchar](max) NULL,
    [origin_subcontinent_name] [nvarchar](max) NULL,
    [continent_origin_name] [nvarchar](max) NULL,
    [origin_eta_date] [datetime2](7) NULL,
    [origin_start] [datetime2](7) NULL,
    [origin_end] [datetime2](7) NULL,
    [destination_country_name] [nvarchar](max) NULL,
    [destination_subcontinent_name] [nvarchar](max) NULL,
    [continent_destination_name] [nvarchar](max) NULL,
    [destination_eta] [datetime2](7) NULL,
    [destination_start] [datetime2](7) NULL,
    [destination_end] [datetime2](7) NULL,
    [lvc] [int] NULL,
    [vessel_delivery_date] [datetime2](7) NULL,
    [vessel_cargo_system] [nvarchar](max) NULL,
    [vessel_cargo_type] [nvarchar](max) NULL,
    [vessel_power_plant] [nvarchar](max) NULL,
    [vessel_id] [int] NULL,
    [trade_link_1_delivery] [nvarchar](max) NULL,
    [trade_link_1_type] [nvarchar](max) NULL,
    [trade_link_1_seller_name] [nvarchar](max) NULL,
    [trade_link_1_seller_country_name] [nvarchar](max) NULL,
    [trade_link_1_buyer_name] [nvarchar](max) NULL,
    [trade_link_1_buyer_country_name] [nvarchar](max) NULL,
    [trade_link_2_delivery] [nvarchar](max) NULL,
    [trade_link_2_type] [nvarchar](max) NULL,
    [trade_link_2_seller_name] [nvarchar](max) NULL,
    [trade_link_2_seller_country_name] [nvarchar](max) NULL,
    [trade_link_2_buyer_name] [nvarchar](max) NULL,
    [trade_link_2_buyer_country_name] [nvarchar](max) NULL,
    [trade_link_3_delivery] [nvarchar](max) NULL,
    [trade_link_3_type] [nvarchar](max) NULL,
    [trade_link_3_seller_name] [nvarchar](max) NULL,
    [trade_link_3_seller_country_name] [nvarchar](max) NULL,
    [trade_link_3_buyer_name] [nvarchar](max) NULL,
    [trade_link_3_buyer_country_name] [nvarchar](max) NULL,
    [trade_link_4_delivery] [nvarchar](max) NULL,
    [trade_link_4_type] [nvarchar](max) NULL,
    [trade_link_4_seller_name] [nvarchar](max) NULL,
    [trade_link_4_seller_country_name] [nvarchar](max) NULL,
    [trade_link_4_buyer_name] [nvarchar](max) NULL,
    [trade_link_4_buyer_country_name] [nvarchar](max) NULL,
    [trade_link_5_delivery] [nvarchar](max) NULL,
    [trade_link_5_type] [nvarchar](max) NULL,
    [trade_link_5_seller_name] [nvarchar](max) NULL,
    [trade_link_5_seller_country_name] [nvarchar](max) NULL,
    [trade_link_5_buyer_name] [nvarchar](max) NULL,
    [trade_link_5_buyer_country_name] [nvarchar](max) NULL,
    [trade_id] [int] NULL,
    [zone_origin_name] [nvarchar](max) NULL,
    [zone_origin_id] [int] NULL,
    [zone_destination_name] [nvarchar](max) NULL,
    [zone_destination_id] [float] NULL,
    [installation_origin_name] [nvarchar](max) NULL,
    [installation_origin_id] [float] NULL,
    [installation_destination_name] [nvarchar](max) NULL,
    [installation_destination_id] [float] NULL,
    [mileage_nautical_miles] [int] NULL,
    [ton_miles] [float] NULL,
    [voyage_id] [int] NULL,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = dbo.[Kpler_Flows_Raw_history]))
GO
