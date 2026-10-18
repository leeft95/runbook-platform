import io

import pandas as pd
import requests
from urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(InsecureRequestWarning)  # type: ignore




class CElink(object):
    url = "https://commodityessentials.com/api/"
    User = ""
    Password = ""
    headers = {"Accept": "text/csv"}
    proxies = ""

    def __init__(self, user, passw, proxies=""):
        self.User = user
        self.Password = passw
        self.proxies = proxies

    def eugasopdata(
        self, assets, variable="", source="", status="", doFilter="", doEstimate="",
        nd="", dateFrom="", dateTo="", unit="", meta="", doOpt="", transform="",
    ):
        """
        eugasopdata, retrieve operational data time series
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection, withdrawal,
                netInjection. or multiple values separated by commas. If omited it will
                return all variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            source: name of the datasource requetsed for the given assets & variables.
                If omited it will return the recommended data source.
                example: 'grtgaz'
            status: refers to alloc, phys, renom, nom. If omited, all will be blended in the
                order alloc > phys > renom > nom.
            doFilter: true/false to indicate the application of quality control filters.
                If omited defaults to true.
            doEstimate: true/false to indicate the estimation of missing datapoints.
                If omited defaults to true.
            nd: Indicates the number of days of history to retrieve.
                If omited will return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent confusion
                between months and days. You can pass the year, e.g. 2014, and it will retrieve
                since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved.
                Please use the format: 01_Jan_2015.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
            doOpt: Indicates that optimized query should be used.
                If omited defaults to false.
            transform: Requests additional transformation to be applied on the data.
                If omited defaults to no transformation. Supported option: pivot_calyoy,
                pivot_gasyoy, month_avg (_sum, _first, _last, _max, _min, _std).
        Returns: dataframe with corresponding time series.
        """
        urlq = self.url + "eugasopdata?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if source != "":
            urlq += "&source=" + source
        if status != "":
            urlq += "&status=" + status
        if doFilter != "":
            urlq += "&doFilter=" + str(doFilter)
        if doEstimate != "":
            urlq += "&doEstimate=" + str(doEstimate)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateFrom)
        if unit != "":
            urlq += "&unit=" + unit
        if meta != "":
            urlq += "&meta=" + str(meta)
        if doOpt != "":
            urlq += "&doOpt=" + str(doOpt)
        if transform != "":
            urlq += "&transform=" + str(transform)
        return self.__execute(urlq)

    def eugasopdata_h(
        self, assets, variable="", source="", status="", doFilter="", doEstimate="",
        nd="", dateFrom="", dateTo="", unit="", meta="", updateSince="", dateFormat="", decimals="",
    ):
        """
        eugasopdata_h, retrieve operational data time series in hourly granularity
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection, withdrawal,
                netInjection. or multiple values separated by commas. If omited it will return
                all variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            source: name of the datasource requetsed for the given assets & variables.
                If omited it will return the recommended data source.
                example: 'grtgaz'
            status: refers to alloc, phys, renom, nom. If omited, all will be blended in the
                order alloc > phys > renom > nom.
            doFilter: true/false to indicate the application of quality control filters.
                If omited defaults to true.
            doEstimate: true/false to indicate the estimation of missing datapoints.
                If omited defaults to true.
            nd: Indicates the number of days of history to retrieve.
                If omited will return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved. Please use the
                format: 01_Jan_2015.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
            updateSince: Pass a date and time to request only points that were updated since.
                Valid formats 21_Apr_2019_0930, 201904210930. The specified time will be
                considered as CET timezone.
            dateFormat: This parameter allows requesting the hourly time to be returned as
                CET, UTC or offset. Defaults to CET.
            decimals: Specify the number of decimals to be returned between 0 and 6.
                The default is 2 decimal places.
        Returns: dataframe with corresponding time series.
        """
        urlq = self.url + "eugasopdata_h?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if source != "":
            urlq += "&source=" + source
        if status != "":
            urlq += "&status=" + status
        if doFilter != "":
            urlq += "&doFilter=" + str(doFilter)
        if doEstimate != "":
            urlq += "&doEstimate=" + str(doEstimate)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateFrom)
        if unit != "":
            urlq += "&unit=" + unit
        if meta != "":
            urlq += "&meta=" + str(meta)
        if updateSince != "":
            urlq += "&updateSince=" + str(updateSince)
        if dateFormat != "":
            urlq += "&dateFormat=" + str(dateFormat)
        if decimals != "":
            urlq += "&decimals=" + str(decimals)
        return self.__execute(urlq)

    def eugasopdatapath(
        self, assets, variable="", source="", status="", doFilter="", doEstimate="",
        nd="", dateFrom="", dateTo="", unit="", dateFor="", dateAtFormat="",
    ):
        """
        eugasopdatapath, retrieve operational data time series
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection, withdrawal,
                netInjection. or multiple values separated by commas. If omited it will
                return all variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            source: name of the datasource requetsed for the given assets & variables.
                If omited it will return the recommended data source.
                example: 'grtgaz'
            status: refers to alloc, phys, renom, nom. If omited, all will be blended in the
                order alloc > phys > renom > nom.
            doFilter: true/false to indicate the application of quality control filters.
                If omited defaults to true.
            doEstimate: true/false to indicate the estimation of missing datapoints.
                If omited defaults to true.
            nd: Indicates the number of days of history to retrieve.
                If omited will return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year,
                e.g. 2014, and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved. Please use the
                format 01_Jan_2015 to prevent confusion between months and days.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            dateFor: Specify a date for which to report the evolution path.
                Please use the format 01_Jan_2015 to prevent confusion between
                months and days.
            dateAtFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
        Returns: dataframe with corresponding time series.
        """
        urlq = self.url + "eugasopdatapath?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if source != "":
            urlq += "&source=" + source
        if status != "":
            urlq += "&status=" + status
        if doFilter != "":
            urlq += "&doFilter=" + str(doFilter)
        if doEstimate != "":
            urlq += "&doEstimate=" + str(doEstimate)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if dateFor != "":
            urlq += "&dateFor=" + str(dateFor)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)
        return self.__execute(urlq)

    def eugasmeta(self, id):
        """
        eugasmeta, retrieve meta data tables
        Parameters
                id: str argument, use either "assets", "series" or "seriesperasset"
        Returns: dataframe with corresponding meta data table.
        """
        urlq = self.url + "eugasmeta?" + "id=" + str(id)
        return self.__execute(urlq)

    def eugasmonthly(
        self, id, nd="", dateFrom="", getLastUpdateTime="", getPath="", filter="", meta=""
    ):
        """
        eugasmonthly, retrieve monthly datasets
        Parameters
            id: corresponding to the unique id of the monthly dataset to retrieve
                use the "Monthly" tab in the dashboard for the list of datasets and id.
            nd: Indicates the number of days of history to retrieve. If omited will return
            the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the time series to be retrieved instead of a
            fixed number of days nd. Please use the format 01_Jan_2015 to prevent confusion
            between months and days. You can pass the year, e.g. 2014, and it will
            retrieve since Jan 1st that year.
            getLastUpfateTime: Use true to request the last update time of a given
            monthly dataset.
            getPath: This parameter can be used (getPath=true) to request the different
            updates for each of the points. This option is supported only for some of
            the datasets such as id=48.
            filter: Optional parameter that can be used for additional filter on the query.
            for example filter=Oseberg will filter the production data to return Oseberg
            field only.
            meta: This option can be used to get the meta table with all monthly datasets.
            This meta table will include the id, description and last update date for
            each of the monthly data sets.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasmonthly?" + "id=" + str(id)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if getLastUpdateTime != "":
            urlq += "&getLastUpdateTime=" + str(getLastUpdateTime)
        if getPath != "":
            urlq += "&getPath=" + str(getPath)
        if filter != "":
            urlq += "&filter=" + str(filter)
        if meta != "":
            urlq += "&meta=" + str(meta)
        return self.__execute(urlq)

    def eugasoverview(
        self, id, nd="", dateFrom="", dateAt="", dateAtStart="", dateAtEnd="",
        dateFor="", dateForStart="", dateForEnd="", filter="", transform="",
    ):
        """
        eugasoverview, retrieve overview datasets
        Parameters
                id: corresponding to the unique id of the overview report to retrieve.
            nd: Indicates the number of days of history to retrieve. If omited will return
            the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the time series to be retrieved instead of a
            fixed number of days nd. Please use the format 01_Jan_2015 to prevent confusion
            between months and days. You can pass the year, e.g. 2014,
            and it will retrieve since Jan 1st that year.
            dateAt: Specify an observation date. This parameter currently applies to
            prismaauctions, gazpromdeliveries.
            dateAtStart: Specify the start of a range of observation dates. This parameter
            currently applies to prismaauctions.
            dateAtEnd: Specify the end of a range of observation dates. This parameter
            currently applies to prismaauctions.
            dateFor: Specify a delivery date. This parameter currently applies to
            prismaauctions, gazpromdeliveriespath. Same formatting requirement as with
            dateFrom.
            dateForStart: Specify a start of delivery period. This parameter currently
            applies to the prismaauctions, gazpromdeliveriespath. Same formatting
            requirement as with dateFrom.
            dateForEnd: Specify a end of delivery period. This parameter currently applies
            to the prismaauctions,gazpromdeliveriespath. Same formatting requirement as
            with dateFrom.
            filter: Specify additional filters applicable for prismaauctions.
            transform: Requests additional transformation to be applied. If omited defaults
            to no transformation. Supported for time series data with the options:
            pivot_calyoy, pivot_gasyoy, month_avg (_sum, _first, _last, _max, _min, _std).
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasoverview?" + "id=" + str(id)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateAt != "":
            urlq += "&dateAt=" + str(dateAt)
        if dateAtStart != "":
            urlq += "&dateAtStart=" + str(dateAtStart)
        if dateAtEnd != "":
            urlq += "&dateAtEnd=" + str(dateAtEnd)
        if dateFor != "":
            urlq += "&dateFor=" + str(dateFor)
        if dateForStart != "":
            urlq += "&dateForStart=" + str(dateForStart)
        if dateForEnd != "":
            urlq += "&dateForEnd=" + str(dateForEnd)
        if filter != "":
            urlq += "&filter=" + str(filter)
        if transform != "":
            urlq += "&transform=" + str(transform)
        return self.__execute(urlq)

    def eugasout(
        self, assets, variable="", nd="", dateFrom="", dateTo="", unit="", dateAt="",
        getDateAt="", getByCol="", capType="", plannedType="", meta="", dateAtFormat="",
    ):
        """
        eugasout, retrieve capacity and outage data for a given asset
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection,
                withdrawal, netInjection. or multiple values separated by commas.
                If omited it will return all variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            nd: Indicates the number of days of history to retrieve. If omited will return
                the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the data to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the data to be retrieved instead of a fixed
                number of days nd. Please use the format 01_Jan_2015 to prevent confusion
                between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            dateAt: optional parameter to request a previous version of this data,
                for example, dateAt=24_Mar_2020_1000. This can be used to compare the
                current latest version with a previous version.
            getDateAt: Pass True to request an additional column to be returned containing
                the last time each of the datapoints was updated.
            dateAtFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
            getByCol: Pass true to request the result to be pivoted into one column per
                series instead of the default view that returns the different types of
                capacity on the same table. Defaults to false.
            capType: Specify the types of capacity to be returned. You can use technical
                for technical capacity, outage or interrupted to the interrupted capacity
                and restricted for the remaining (technical-outage) capacity.
                Multiple options can be requested separated by comma (e.g. technical,outage).
                If this parameter is not used all types will be returned.
            plannedType: Specify the types of outage to be returned. You can use planned,
                unplanned, actual or total. Multiple options can be requested separated
                by comma (e.g. planned,unplanned,total). If this parameter is not used
                all types will be returned.
            meta: When true, will only return the header meta data rows. If omited
                defaults to false.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasout?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if dateAt != "":
            urlq += "&dateAt=" + str(dateAt)
        if getDateAt != "":
            urlq += "&getDateAt=" + str(getDateAt)
        if getByCol != "":
            urlq += "&getByCol=" + str(getByCol)
        if capType != "":
            urlq += "&capType=" + str(capType)
        if plannedType != "":
            urlq += "&plannedType=" + str(plannedType)
        if meta != "":
            urlq += "&meta=" + str(meta)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)

        return self.__execute(urlq)

    def eugasoutbulk(
        self, nd="", dateFrom="", dateTo="", unit="", getDateAt="", updateSince="",
        updateTo="", dateAtFormat="", capType="", plannedType="",
    ):
        """
        eugasoutbulk, retrieve the capacity and outage data for all assets on a given
            date interval. Being a bulk download the size of the date range is limited
            to 150 days. This 150d limitation will not apply when using updateSince
            parameter with a value within the last 5 days.
        Parameters
            nd: Indicates the number of days of history to retrieve ending today.
                If omited it will default to 7 days. The maximum allowed is 14 days.
            dateFrom: Specify a start date for the bulk download to be retrieved instead
                of a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the bulk download to be retrieved instead
                of a fixed number of days nd. Please use the format 01_Jan_2015 to
                prevent confusion between months and days. You can pass the year, e.g.
                2014, and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            getDateAt: Pass "true" to request an additional column to be returned
                containing the last time each of the datapoints was updated.
            dateAtFormat: This parameter allows requesting the hourly time to be
                returned as CET, UTC or offset. Defaults to CET.
            updateSince: Pass a date and time to request only points that were updated
                since. Valid formats 21_Apr_2019_0930, 201904210930, today-3.
                The specified time will be considered as CET timezone.
            updateTo: Pass a date and time to request only points that were updated
                up to that time. Valid formats 21_Apr_2019_0930, 201904210930, today,
                today-2, now, now-2h. The specified time will be considered as
                CET timezone.
            capType: Specify the types of capacity to be returned. You can use technical
                for technical capacity, outage or interrupted to the interrupted
                capacity and restricted for the remaining (technical-outage) capacity.
                Multiple options can be requested separated by comma (e.g. technical,outage).
                If this parameter is not used all types will be returned.
            plannedType: Specify the types of outage to be returned. You can use planned,
                unplanned, actual or total. Multiple options can be requested separated
                by comma (e.g. planned,unplanned,total). If this parameter is not used
                all types will be returned.
        Returns: dataframe with corresponding dataset, including the same columns as
            the eugasout method.
        """
        urlq = self.url + "eugasoutbulk"
        if nd != "":
            urlq += "?nd=" + str(nd)
        if dateFrom != "":
            if nd != "":
                urlq += "&dateFrom=" + str(dateFrom)
            else:
                urlq += "?dateFrom=" + str(dateFrom)
        if dateTo != "":
            if nd != "" or dateFrom != "":
                urlq += "&dateTo=" + str(dateTo)
            else:
                urlq += "?dateTo=" + str(dateTo)
        if unit != "":
            if nd != "" or dateFrom != "" or dateTo != "":
                urlq += "&unit=" + unit
            else:
                urlq += "?unit=" + unit
        if updateSince != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "":
                urlq += "&updateSince=" + updateSince
            else:
                urlq += "?updateSince=" + updateSince
        if updateTo != "":
            urlq += "&updateTo=" + str(updateTo)
        if getDateAt != "":
            urlq += "&getDateAt=" + str(getDateAt)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)
        if capType != "":
            urlq += "&capType=" + str(capType)
        if plannedType != "":
            urlq += "&plannedType=" + str(plannedType)

        return self.__execute(urlq)

    def eugasoutpath(
        self, assets, variable="", nd="", dateFrom="", dateTo="", unit="", capType="",
        plannedType="", meta="", dateAtFormat="",
    ):
        """
        [TRANSCRIPTION: source description line 598 is clipped.]
            its updates represented with different dateAt
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection,
                withdrawal, netInjection.
                or multiple values separated by commas. If omited it will return all
                variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            nd: Indicates the number of days of history to retrieve. If omited will
                return the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the data to be retrieved instead of a
                fixed number of days nd. Please use the format 01_Jan_2015 to
                prevent confusion between months and days. You can pass the year,
                e.g. 2014, and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the data to be retrieved instead of a
                fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            dateAtFormat: This parameter allows requesting the hourly time to be
                returned as CET, UTC or offset. Defaults to CET.
            capType: Specify the types of capacity to be returned. You can use technical
                for technical capacity, outage or interrupted to the interrupted capacity
                and restricted for the remaining (technical-outage) capacity. Multiple
                options can be requested separated by comma (e.g. technical,outage).
                If this parameter is not used all types will be returned.
            plannedType: Specify the types of outage to be returned. You can use planned,
                unplanned, actual or total. Multiple options can be requested separated by
                comma (e.g. planned,unplanned,total). If this parameter is not used all
                types will be returned.
            meta: When true, will only return the header meta data rows. If omited
                defaults to false.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasoutpath?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if capType != "":
            urlq += "&capType=" + str(capType)
        if plannedType != "":
            urlq += "&plannedType=" + str(plannedType)
        if meta != "":
            urlq += "&meta=" + str(meta)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)

        return self.__execute(urlq)

    def eugasoutevents(
        self, assets="", variable="", source="", nd="", unit="", dateAt="", dateAtStart="",
        dateAtEnd="", dateFor="", dateForStart="", dateForEnd="",
    ):
        """
        eugasoutevents, retrieve outage data in the form of individual outge events
            including their different updates.
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection,
                withdrawal, netInjection.
                or multiple values separated by commas. If omited it will return all
                variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            source: select the data source that published the outages. For example:
                'gassco' or 'natgrid remit'
            nd: Indicates the number of days of history to retrieve. If omited will
                return the standard number of days for each overview.
                        Example: gbentryflows.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            dateAt: optional parameter to request events published up to a certain time,
                for example, dateAt=24_Mar_2020_1000.
            dateAtStart: optional parameter to request events published starting from a
                certain time, for example, dateAtStart=24_Mar_2020_1000.
            dateAtEnd: optional parameter to request events published up to a certain time,
                for example, dateAtEnd=24_Mar_2020_1000.
            dateFor: optional parameter to request events published affecting a particular
                gasDay, for example, dateFor=24_Mar_2020.
            dateForStart: optional parameter to request events that affect a certain
                gasDay or later, for example, dateForStart=24_Mar_2020.
            dateForEnd: optional parameter to request events that affect a certain
                gasDay or earlier, for example, dateForEnd=24_Mar_2020.

        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasoutevents?source=" + str(source)
        if assets != "":
            urlq += "&assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + str(variable)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if unit != "":
            urlq += "&unit=" + unit
        if dateAt != "":
            urlq += "&dateAt=" + dateAt
        if dateAtStart != "":
            urlq += "&dateAtStart=" + dateAtStart
        if dateAtEnd != "":
            urlq += "&dateAtEnd=" + dateAtEnd
        if dateFor != "":
            urlq += "&dateFor=" + dateFor
        if dateForStart != "":
            urlq += "&dateForStart=" + dateForStart
        if dateForEnd != "":
            urlq += "&dateForEnd=" + dateForEnd

        return self.__execute(urlq)

    def eugasseries(
        self, id, nd="", dateFrom="", dateTo="", unit="", meta="", transform="", dateAt=""
    ):
        """
        eugasseries, retrieve a set of time series identified by their id codes.
        Parameters
            id: Time series identifier (see 'series' meta table).
                examples: '19950', '19950,27858'
            nd: Indicates the number of days of history to retrieve. If omited will
                return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead
                of a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
            transform: Requests additional transformation to be applied on the data.
                If omited defaults to no transformation. Supported option: pivot_calyoy,
                pivot_gasyoy, month_avg (_sum, _first, _last, _max, _min, _std).
            dateAt: optional parameter to request a previous version of this data,
                for example, dateAt=24_Mar_2020_1000. This can be used to compare the
                current latest version with a previous version.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasseries?" + "id=" + str(id)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if meta != "":
            urlq += "&meta=" + str(meta)
        if transform != "":
            urlq += "&transform=" + str(transform)
        if dateAt != "":
            urlq += "&dateAt=" + str(dateAt)

        return self.__execute(urlq)

    def eugasseries_h(
        self, id, nd="", dateFrom="", dateTo="", unit="", meta="", updateSince="",
        dateFormat="", decimals="",
    ):
        """
        eugasseries_h, retrieve a set of hourly granularity time series identified by
            their id codes.
        Parameters
            id: Time series identifier (see 'series' meta table).
                examples: '19950', '19950,27858'
            nd: Indicates the number of days of history to retrieve. If omited will
                return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
            updateSince: Pass a date and time to request only points that were updated
                since. Valid formats 21_Apr_2019_0930, 201904210930. The specified time
                will be considered as CET timezone.
            dateFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
            decimals: Specify the number of decimals to be returned between 0 and 6.
                The default is 2 decimal places.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasseries_h?" + "id=" + str(id)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if meta != "":
            urlq += "&meta=" + str(meta)
        if updateSince != "":
            urlq += "&updateSince=" + str(updateSince)
        if dateFormat != "":
            urlq += "&dateFormat=" + str(dateFormat)
        if decimals != "":
            urlq += "&decimals=" + str(decimals)
        return self.__execute(urlq)

    def eugasseriespath(
        self, id, nd="", dateFrom="", dateTo="", unit="", dateFor="", dateAtFormat=""
    ):
        """
        eugasseriespath, retrieve the updates for a given set of points of time series
            identified by their id codes.
        Parameters
            id: Time series identifier (see 'series' meta table).
                examples: '19950', '19950,27858'
            nd: Indicates the number of days of history to retrieve. If omited will
                return all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            dateFor: Specify a date for which to report the evolution path.
                Please use the format 01_Jan_2015 to prevent confusion
                between months and days.
            dateAtFormat: This parameter allows requesting the hourly time to be
                returned as CET, UTC or offset. Defaults to CET.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasseriespath?" + "id=" + str(id)
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if dateFor != "":
            urlq += "&dateFor=" + str(dateFor)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)
        return self.__execute(urlq)

    def eugasseriesbulk(
        self, nd="", dateFrom="", dateTo="", unit="", series="", getStatus="", getSource="",
        getUnit="", getDateAt="", updateSince="", updateTo="", dateAtFormat="",
    ):
        """
        eugasseriesbulk, retrieve the values for all series Id on a given date interval.
            Being a bulk download the size of the date range is limited to 14 days.
        Parameters
            nd: Indicates the number of days of history to retrieve ending today.
                If omited it will default to 7 days. The maximum allowed is 14 days.
            dateFrom: Specify a start date for the bulk download to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the bulk download to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            series: This parameter allows to select an individual series or group of series.
                You can pass the Id of an individual series or a group of series Id
                separated by comma. You can also pass the codeword "blend" which will
                return all the recommended series, i.e. passing series=blend will return
                data for all series in which statusBlend=true, sourceBlend=true,
                doFilter=true, doEstimate=true, excludeNoms=false.
            getStatus: Pass "true" to request an additional column to be returned
                containing the status (nom, phys, alloc,...) for each of the datapoints.
            getSouce: Pass "true" to request an additional column to be returned containing
                the source for each of the datapoints.
            getUnit: Pass "true" to request an additional column to be returned containing
                the unit for each of the datapoints.
            getDateAt: Pass "true" to request an additional column to be returned
                containing the last time each of the datapoints was updated.
            dateAtFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
            updateSince: Pass a date and time to request only points that were updated
                since. Valid formats 21_Apr_2019_0930, 201904210930, today, today-2,
                now-2h. The specified time will be considered as CET timezone.
            updateTo: Pass a date and time to request only points that were updated up
                to that time. Valid formats 21_Apr_2019_0930, 201904210930, today,
                today-2, now, now-2h. The specified time will be considered as CET timezone.
        Returns: dataframe with corresponding dataset, including the date, the series
            Id and the corresponding value.
        """
        urlq = self.url + "eugasseriesbulk"
        if nd != "":
            urlq += "?nd=" + str(nd)
        if dateFrom != "":
            if nd != "":
                urlq += "&dateFrom=" + str(dateFrom)
            else:
                urlq += "?dateFrom=" + str(dateFrom)
        if dateTo != "":
            if nd != "" or dateFrom != "":
                urlq += "&dateTo=" + str(dateTo)
            else:
                urlq += "?dateTo=" + str(dateTo)
        if unit != "":
            if nd != "" or dateFrom != "" or dateTo != "":
                urlq += "&unit=" + unit
            else:
                urlq += "?unit=" + unit
        if series != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "":
                urlq += "&series=" + str(series)
            else:
                urlq += "?series=" + str(series)
        if getStatus != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "":
                urlq += "&getStatus=" + str(getStatus)
            else:
                urlq += "?getStatus=" + str(getStatus)
        if getSource != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "":
                urlq += "&getSource=" + str(getSource)
            else:
                urlq += "?getSource=" + str(getSource)
        if getUnit != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "":
                urlq += "&getUnit=" + str(getUnit)
            else:
                urlq += "?getUnit=" + str(getUnit)
        if getDateAt != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "":
                urlq += "&getDateAt=" + str(getDateAt)
            else:
                urlq += "?getDateAt=" + str(getDateAt)
        if updateSince != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "" or getDateAt != "":
                urlq += "&updateSince=" + str(updateSince)
            else:
                urlq += "?updateSince=" + str(updateSince)
        if updateTo != "":
            urlq += "&updateTo=" + str(updateTo)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)
        return self.__execute(urlq)

    def eugasseriesbulk_h(
        self, nd="", dateFrom="", dateTo="", unit="", series="", getStatus="", getSource="",
        getUnit="", updateSince="", dateFormat="", getDateAt="", decimals="",
    ):
        """
        eugasseriesbulk_h, retrieve the values, in daily granularity, for all series
            Id on a given date interval. Being a bulk download the size of the date
            range is limited to 14 days.
        Parameters
            nd: Indicates the number of days of history to retrieve ending today.
                If omited it will default to 7 days. The maximum allowed is 14 days.
            dateFrom: Specify a start date for the bulk download to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the bulk download to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            series: This parameter allows to select an individual series or group of
                series. You can pass the Id of an individual series or a group of series
                Id separated by comma. You can also pass the codeword "blend" which will
                return all the recommended series, i.e. passing series=blend will return
                data for all series in which statusBlend=true, sourceBlend=true,
                doFilter=true, doEstimate=true, excludeNoms=false.
            getStatus: Pass "true" to request an additional column to be returned
                containing the status (nom, phys, alloc,...) for each of the datapoints.
            getSouce: Pass "true" to request an additional column to be returned
                containing the source for each of the datapoints.
            getUnit: Pass "true" to request an additional column to be returned
                containing the unit for each of the datapoints.
            updateSince: Pass a date and time to request only points that were
                updated since. Valid formats 21_Apr_2019_0930, 201904210930.
                The specified time will be considered as CET timezone.
            dateFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
            getDateAt: Pass "true" to request an additional column to be returned
                containing the date and time when each datapoint was last updated.
                This date and time can be formatted using the dateFormat option.
            decimals: Specify the number of decimals to be returned between 0 and 6.
                The default is 2 decimal places.
        Returns: dataframe with corresponding hourly dataset, including the date and time,
            the series Id and the corresponding value.
        """
        urlq = self.url + "eugasseriesbulk_h"
        if nd != "":
            urlq += "?nd=" + str(nd)
        if dateFrom != "":
            if nd != "":
                urlq += "&dateFrom=" + str(dateFrom)
            else:
                urlq += "?dateFrom=" + str(dateFrom)
        if dateTo != "":
            if nd != "" or dateFrom != "":
                urlq += "&dateTo=" + str(dateTo)
            else:
                urlq += "?dateTo=" + str(dateTo)
        if unit != "":
            if nd != "" or dateFrom != "" or dateTo != "":
                urlq += "&unit=" + unit
            else:
                urlq += "?unit=" + unit
        if series != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "":
                urlq += "&series=" + series
            else:
                urlq += "?series=" + str(series)
        if getStatus != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "":
                urlq += "&getStatus=" + str(getStatus)
            else:
                urlq += "?getStatus=" + str(getStatus)
        if getSource != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "":
                urlq += "&getSource=" + str(getSource)
            else:
                urlq += "?getSource=" + str(getSource)
        if getUnit != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "":
                urlq += "&getUnit=" + str(getUnit)
            else:
                urlq += "?getUnit=" + str(getUnit)
        if updateSince != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "":
                urlq += "&updateSince=" + str(updateSince)
            else:
                urlq += "?updateSince=" + str(updateSince)
        if dateFormat != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "" or updateSince != "":
                urlq += "&dateFormat=" + str(dateFormat)
            else:
                urlq += "?dateFormat=" + str(dateFormat)
        if getDateAt != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "" or updateSince != "" or dateFormat != "":
                urlq += "&getDateAt=" + str(getDateAt)
            else:
                urlq += "?getDateAt=" + str(getDateAt)
        if decimals != "":
            if nd != "" or dateFrom != "" or dateTo != "" or unit != "" or series != "" or getStatus != "" or getSource != "" or getUnit != "" or updateSince != "" or dateFormat != "" or getDateAt != "":
                urlq += "&decimals=" + str(decimals)
            else:
                urlq += "?decimals=" + str(decimals)
        return self.__execute(urlq)

    def eugascountry(self, id, nd="", dateFrom="", unit="", meta="", dateTo=""):
        """
        eugascountry, retrieve a set of time series corresponding to a country
        [TRANSCRIPTION: description continuation and Parameters line 1197-1199 clipped.]
            id: Country two letter ISO code:
                examples: 'GB', 'FR'
            nd: Indicates the number of days of history to retrieve.
                If omited will return all available data.
            dateFrom: Specify a start date for the time series to be retrieved
                instead of a fixed number of days nd. Please use the format 01_Jan_2015
                to prevent confusion between months and days. You can pass the year,
                e.g. 2014, and it will retrieve since Jan 1st that year. Dates relative
                to today are possible, e.g. "today", "today-30"
            dateTo: Specify an end date for the time series to be retrieved.
                Please use the format 01_Jan_2015 to prevent confusion between months
                and days. You can pass the year, e.g. 2014, and it will retrieve since
                Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugascountry?" + "id=" + id
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + unit
        if meta != "":
            urlq += "&meta=" + str(meta)
        return self.__execute(urlq)

    def eugasaudit(self, id, nd="", dateFrom="", unit="", meta="", dateTo=""):
        """
        eugasaudit, retrieves the collection of all raw datasets available for a given asset.
            The purpose of this method is to compere the different data sources and status
            available for a given asset.
            This will include all raw data series available for the asset taking into
            account different variables, data sources and data point status.
        Parameters
            id: asset id to be queried.
            nd: Indicates the number of days of history to retrieve. If omited will return
            all available data.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved. Please use
                the format 01_Jan_2015 to prevent confusion between months and days.
                You can pass the year, e.g. 2014, and it will retrieve since Jan 1st
                that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugasaudit?" + "id=" + id
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + str(unit)
        if meta != "":
            urlq += "&meta=" + str(meta)
        return self.__execute(urlq)

    def eugascapbooking(
        self, assets, variable="", capType="", bookStatus="", nd="", dateFrom="", dateTo="",
        unit="", getDir="", getMatch="", getByCol="", dateAt="", getDateAt="", updateSince="",
        updateTo="", source="", meta="", bookDir="", bookTso="", dateAtFormat="",
    ):
        """
        eugascapbooking, retrieve capacity bookings data for a given asset. This data is
            split by capacity type (firm/interruptible), booking status (booked/available)
            and booking tenure (M,Q,Y,etc) when available.
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection,
                withdrawal, netInjection.
                or multiple values separated by commas. If omited it will return all
                variables available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            capType: Optional parameter to filter the type of capacity: firm, interruptible.
            bookStatus: Optional parameter to filter the booking status of the capacity:
                booked, available.
            bookDir: Optional parameter to filter the direction of the capacity: exit,
                entry or exitentry.
            bookTso: Optional parameter to filter the TSO: use the name or start of the
                name that identifies the TSO.
            source: Optional parameter. Use source=prisma to request bookings based on the
                sum of prisma auctions. By default bookints will be based on TSO or Entsog
                published total bookings. Note the prisma based bookings is not generally
                available for all points.
            nd: Indicates the number of days of history to retrieve. If omited will return
                the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            getDir: Use true or false to request the result to be split by entry and exit
                direction as well as TSO. This will add two additional columns to the
                result indicating the direction and the TSO.
            getMatch: Use getMatch=true to request the capacityBooking data to include a
                breakdown for the Entry and Exit directions and also indicating if the
                bookings are matched or unmatched.
            getByCol: Use getByCol=true to request the resulting table to be presented
                pivoted into different columns.
            dateAt: Pass a date and time to request a previous version of the data with
                the information available up to that moment. This feature is available
                only when using the option getDir=true and is not available at the moment
                for getMatch=true. Since this is a recent feature values for dateAt
                parameter should be after 8th July 2020. Valid formats 11_Jul_2020_0930,
                202007110930. The specified time will be considered as CET timezone.
            getDateAt: Pass true to request a column with the data and time (CET) indicating
                the last time each row was updated.
            dateAtFormat: This parameter allows requesting the hourly time to be returned
                as CET, UTC or offset. Defaults to CET.
            updateSince: Pass a date and time to request only points that were updated
                since. Valid formats 15_Jul_2020_0930, 202007150930, today-2. The specified
                time will be considered as CET timezone. Since this is a recent feature
                values for updateSince parameter should be after 8th July 2020.
                If you use this parameter with a value within the last 5 days,
                this query ensures that all updated points since that time will be returned.
            updateTo: Pass a date and time to request only points that were updated up
                to that time. Valid formats 21_Apr_2019_0930, 201904210930, today,
                today-2, now, now-2h. The specified time will be considered as CET timezone.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugascapbooking?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if capType != "":
            urlq += "&capType=" + capType
        if bookStatus != "":
            urlq += "&bookStatus=" + bookStatus
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + str(unit)
        if getDir != "":
            urlq += "&getDir=" + str(getDir)
        if getMatch != "":
            urlq += "&getMatch=" + str(getMatch)
        if getByCol != "":
            urlq += "&getByCol=" + str(getByCol)
        if dateAt != "":
            urlq += "&dateAt=" + str(dateAt)
        if getDateAt != "":
            urlq += "&getDateAt=" + str(getDateAt)
        if updateSince != "":
            urlq += "&updateSince=" + str(updateSince)
        if updateTo != "":
            urlq += "&updateTo=" + str(updateTo)
        if source != "":
            urlq += "&source=" + str(source)
        if meta != "":
            urlq += "&meta=" + str(meta)
        if bookDir != "":
            urlq += "&bookDir=" + str(bookDir)
        if bookTso != "":
            urlq += "&bookTso=" + str(bookTso)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)

        return self.__execute(urlq)

    def eugascapbookingpath(
        self, assets, variable="", capType="", bookStatus="", nd="", dateFrom="", dateTo="",
        unit="", getDir="", updateSince="", updateTo="", source="", meta="", bookDir="",
        bookTso="", dateAtFormat="",
    ):
        """
        eugascapbookingpath, Query the sequence of updates to the capacity booking data.
        Currently this type of query works only for the getDir=true configuration.
        Returns a detailed table with capacity booking information including firm vs
        interruptible capacity, booked vs available capacity.
        This API includes the multiple updates to the capacity booking data for a given asset.
        Each time a datapoint is updated this is indicated with a different dateAt.
        Parameters
            assets: assetQuery that determines the gas assets for which to return data.
                examples: '47', '47,48', 'gb_nl', 'fr_reg', 'fr,be_reg', 'it_ch'
            variable: can be netFlow, forwardFlow, reverseFlow, stock, injection, withdrawal,
                netInjection.
                or multiple values separated by commas. If omited it will return all variables
                available for the assets.
                example: 'netFlow,forwardFlow,reverseFlow' or 'stock,netInjection'
            capType: Optional parameter to filter the type of capacity: firm, interruptible.
            bookStatus: Optional parameter to filter the booking status of the capacity:
                booked, available.
            bookDir: Optional parameter to filter the direction of the capacity: exit,
                entry or exitentry.
            bookTso: Optional parameter to filter the TSO:
                use the name or start of the name that identifies the TSO.
            source: Optional parameter. Use source=prisma to request bookings based on
                the sum of prisma auctions. By default bookints will be based on TSO or
                Entsog published total bookings. Note the prisma based bookings is not
                generally available for all points.
            nd: Indicates the number of days of history to retrieve.
                If omited will return the standard number of days for each overview.
                        Example: gbentryflows.
            dateFrom: Specify a start date for the time series to be retrieved instead
                of a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014,
                and it will retrieve since Jan 1st that year.
            dateTo: Specify an end date for the time series to be retrieved instead of
                a fixed number of days nd. Please use the format 01_Jan_2015 to prevent
                confusion between months and days. You can pass the year, e.g. 2014, and
                it will retrieve since Jan 1st that year.
            unit: 'mcm' or 'GWh' to indicate the units of measurement for the result.
                If omited, defaults to mcm.
            getDir: Use getDir=true to request the capacityBooking data to include a breakdown
                for the Entry and Exit directions. This API currently works only with
                    directional bookings and it will default to getDir=true if you don't
                    use this argument.
            updateSince: Pass a date and time to request only points that were updated since.
                Valid formats 15_Jul_2020_0930, 202007150930, today-2. The specified time will
                be considered as CET timezone. Since this is a recent feature values for updateSince
                parameter should be after 8th July 2020. If you use this parameter with a value
                within the last 5 days, this query ensures that all updated points since that
                time will be returned.
            updateTo: Pass a date and time to request only points that were updated up to that time.
                Valid formats 21_Apr_2019_0930, 201904210930, today, today-2, now, now-2h.
                The specified time will be considered as CET timezone.
            meta: true/false. When true, will only return the header meta data rows.
                If omited defaults to false.
            dateAtFormat: This parameter allows requesting the hourly time to be returned as CET,
                UTC or offset. Defaults to CET.
        Returns: dataframe with corresponding dataset.
        """
        urlq = self.url + "eugascapbookingpath?" + "assets=" + str(assets)
        if variable != "":
            urlq += "&variable=" + variable
        if capType != "":
            urlq += "&capType=" + capType
        if bookStatus != "":
            urlq += "&bookStatus=" + bookStatus
        if nd != "":
            urlq += "&nd=" + str(nd)
        if dateFrom != "":
            urlq += "&dateFrom=" + str(dateFrom)
        if dateTo != "":
            urlq += "&dateTo=" + str(dateTo)
        if unit != "":
            urlq += "&unit=" + str(unit)
        if getDir != "":
            urlq += "&getDir=" + str(getDir)
        if updateSince != "":
            urlq += "&updateSince=" + str(updateSince)
        if updateTo != "":
            urlq += "&updateTo=" + str(updateTo)
        if source != "":
            urlq += "&source=" + str(source)
        if meta != "":
            urlq += "&meta=" + str(meta)
        if bookDir != "":
            urlq += "&bookDir=" + str(bookDir)
        if bookTso != "":
            urlq += "&bookTso=" + str(bookTso)
        if dateAtFormat != "":
            urlq += "&dateAtFormat=" + str(dateAtFormat)

        return self.__execute(urlq)

    def __execute(self, urlq):
        if self.proxies != "":
            r = requests.get(
                urlq,
                auth=(self.User, self.Password),
                headers=self.headers,
                proxies=self.proxies,
                verify=False,
            )
        else:
            r = requests.get(
                urlq, auth=(self.User, self.Password), headers=self.headers, verify=False
            )
        s = r.text

        if r.status_code != 200:
            print(f"[CE API] HTTP Error {r.status_code} for URL: {urlq[:150]}...")
            print(f"[CE API] Response (first 1000 chars):\n{s[:1000]}")
            raise RuntimeError(
                f"CE API returned HTTP {r.status_code}. Check credentials and connectivity."
            )

        try:
            dataf = pd.read_csv(io.StringIO(s), sep=None, engine="python")
        except pd.errors.ParserError as e:
            print("[CE API] ParserError - API returned invalid CSV data")
            print(f"[CE API] URL: {urlq[:200]}...")
            print(f"[CE API] HTTP Status: {r.status_code}")
            print(f"[CE API] Response (first 1500 chars):\n{s[:1500]}")
            print(f"[CE API] Parser error: {e}")
            raise RuntimeError(
                "CE API returned invalid CSV data. This usually means the API "
                "returned an error page, HTML, or malformed response. "
                f"Check credentials, connectivity, and rate limits. Original error: {e}"
            ) from e

        return dataf

    def pmmarkets(self):
        """
        pmmarkets, retrieve the list of markets available in this API
        The code names in the first column are the identifiers that
        can be used for each market on the different PM API methods.
        """
        urlq = self.url + "pmmarkets"
        return self.__execute(urlq)

    def pmcontract(
        self, id, dateAt="", dateAtStart="", dateAtEnd="", dateFor="", dateForStart="",
        dateForEnd="", nd="",
    ):
        """
        pmcontract, retrieve price data based on contracts
        Parameters
            id: string requesting a market and contract.
                examples:
                NBP_Sum.19 will return the historical prices for this particular contract
                NBP_Sum   will return the historical prices for all Summer contracts
                NBP_Mar-Q3    will return the historical prices for the Mar-Q3 spread in all years.
                NBP_spot returns the daily spot or outturn price for this market.

                Multiple structures can be requested on the same query separated by commas:
                NBP_spot,NBP_Sum.19,Brent_Jun.19,JKM_Aug.19

            dateAt: This date represents the market date or pricing mark date.
            This parameter allows to filter a specific market date, e.g. '1_Oct_2018'
            dateAtStart: defines a starting date for a range of market dates to be returned,
                e.g. '1_Oct_2018'
            dateAtEnd: defines an ending date for a range of market dates to be returned,
                e.g. '31_Dec_2019'
            dateFor: This date represents the delivery date for the different forward contracts.
            This parameter allows to filter a specific forward contract, e.g.
            '1_Mar_2019' will select the Mar.19 contract.
            dateForStart: defines the most prompt contract to be returned
            dateForEnd: defines the last, further out in delivery, contract to be returned.
            nd: return prices as a rolling window of most recent days, e.g.
            nd=100 will return the prices in the last 100 days.
        Returns: dataframe with corresponding time series.
        """
        urlq = self.url + "pmcontract?" + "id=" + str(id)
        if dateAt:
            urlq += "&dateAt=" + dateAt
        if dateAtStart:
            urlq += "&dateAtStart=" + dateAtStart
        if dateAtEnd:
            urlq += "&dateAtEnd=" + dateAtEnd
        if dateFor:
            urlq += "&dateFor=" + dateFor
        if dateForStart:
            urlq += "&dateForStart=" + dateForStart
        if dateForEnd:
            urlq += "&dateForEnd=" + dateForEnd
        if nd != "":
            urlq += "&nd=" + str(nd)
        return self.__execute(urlq)
