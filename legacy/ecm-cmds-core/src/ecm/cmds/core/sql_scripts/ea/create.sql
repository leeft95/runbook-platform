USE LO25

create schema ea
GO

CREATE TABLE [ea].[metadata](
    [id] int not null identity primary key clustered,
    [dataset_id] int not null,
    [dataset_name] [nvarchar](max) not null,
    [licensed] bit not null,
    [description] [nvarchar](max) null,
    [source] [nvarchar](max) null,
    [date_from_min] datetime2 null,
    [date_to_max] datetime2 null,
    [aspect] [nvarchar](max) null,
    [aspect_subtype] [nvarchar](max) null,
    [category] [nvarchar](max) null,
    [category_subtype] [nvarchar](max) null,
    [frequency] [nvarchar](max) null,
    [lifecycle_stage] [nvarchar](max) null,
    [region] [nvarchar](max) null,
    [unit] [nvarchar](max) null,
    [country] [nvarchar](max) null,
    [country_iso] [nvarchar](max) null,
    [sub_region] [nvarchar](max) null,
    [t0] datetime2 generated always as row start,
    [t1] datetime2 generated always as row end,
    period for system_time ([t0], [t1])
) with (system_versioning=on (history_table = ea.[metadata_history]))
GO
