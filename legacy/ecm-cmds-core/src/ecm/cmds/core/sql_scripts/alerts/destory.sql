USE lo25
GO

IF EXISTS (SELECT * FROM information_schema.TABLES WHERE table_schema='alerts' AND table_name='config')
    ALTER TABLE alerts.config SET (SYSTEM_VERSIONING = OFF)
GO
DROP TABLE IF EXISTS alerts.config
GO
DROP TABLE IF EXISTS alerts.config_history
GO

IF EXISTS (SELECT * FROM information_schema.TABLES WHERE table_schema='alerts' AND table_name='live')
    ALTER TABLE alerts.live SET (SYSTEM_VERSIONING = OFF)
GO
DROP TABLE IF EXISTS alerts.live
GO
DROP TABLE IF EXISTS alerts.live_history
GO

IF EXISTS (SELECT * FROM information_schema.TABLES WHERE table_schema='alerts' AND table_name='alert_type')
    ALTER TABLE alerts.alert_type SET (SYSTEM_VERSIONING = OFF)
GO
DROP TABLE IF EXISTS alerts.alert_type
GO
DROP TABLE IF EXISTS alerts.alert_type_history
GO

DROP SCHEMA IF EXISTS alerts
GO
