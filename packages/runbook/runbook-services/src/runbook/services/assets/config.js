(function () {
    "use strict";

    const dagFunctions = window.dashAgGridFunctions =
        window.dashAgGridFunctions || {};

    dagFunctions.mappingSummary = function (value) {
        if (!value || typeof value !== "object") {
            return "Configure";
        }

        const entries = Object.entries(value);

        if (entries.length === 0) {
            return "Configure";
        }

        if (entries.length === 1) {
            const [alias, target] = entries[0];

            const datasetId =
                target && typeof target === "object"
                    ? target.dataset_id
                    : target;

            return `${alias} → ${datasetId || "?"}`;
        }

        return `${entries.length} mappings`;
    };

    dagFunctions.jsonSummary = function (value) {
        if (!value || typeof value !== "object") {
            return "Empty";
        }

        const keys = Object.keys(value);

        if (keys.length === 0) {
            return "Empty";
        }

        if (keys.length <= 2) {
            return keys.join(", ");
        }

        return `${keys.slice(0, 2).join(", ")} +${keys.length - 2}`;
    };

    dagFunctions.scheduleSummary = function (schedule) {
        const value = schedule && typeof schedule === "object" ? schedule : {};
        const cron = String(value.cron || "").trim();
        const timezone = String(value.timezone || "UTC").trim() || "UTC";

        if (!cron) {
            return "Configure";
        }

        const everyNHours = cron.match(/^(\d+)\s+\*\/(\d+)\s+\*\s+\*\s+\*$/);
        if (everyNHours) {
            const minute = Number(everyNHours[1]);
            const interval = Number(everyNHours[2]);
            const suffix = minute ? ` @ :${String(minute).padStart(2, "0")}` : "";
            return `Every ${interval}h${suffix} · ${timezone}`;
        }

        const parts = cron.split(/\s+/);
        if (parts.length === 5) {
            const [minute, hour, dom, month, dow] = parts;
            const minuteNumber = Number(minute);
            const hourNumber = Number(hour);

            if (
                /^\d+$/.test(minute) &&
                hour === "*" &&
                dom === "*" &&
                month === "*" &&
                dow === "*"
            ) {
                return `Hourly @ :${String(minuteNumber).padStart(2, "0")} · ${timezone}`;
            }

            if (
                /^\d+$/.test(minute) &&
                /^\d+$/.test(hour) &&
                dom === "*" &&
                month === "*" &&
                dow === "*"
            ) {
                return `Daily ${String(hourNumber).padStart(2, "0")}:${String(minuteNumber).padStart(2, "0")} · ${timezone}`;
            }

            if (
                /^\d+$/.test(minute) &&
                /^\d+$/.test(hour) &&
                dom === "*" &&
                month === "*" &&
                dow === "1-5"
            ) {
                return `Weekdays ${String(hourNumber).padStart(2, "0")}:${String(minuteNumber).padStart(2, "0")} · ${timezone}`;
            }
        }

        return `${cron} · ${timezone}`;
    };

    function buildCron(mode, minute, hour, interval, dow, dom, custom) {
        const selectedMode = mode || "daily";
        const selectedMinute = minute == null ? 0 : Number(minute);
        const selectedHour = hour == null ? 0 : Number(hour);
        const selectedInterval = interval == null ? 6 : Number(interval);
        const selectedDow = dow || "1";
        const selectedDom = dom == null ? 1 : Number(dom);

        if (!Number.isInteger(selectedMinute) || selectedMinute < 0 || selectedMinute > 59) {
            throw new Error("minute must be 0..59");
        }
        if (!Number.isInteger(selectedHour) || selectedHour < 0 || selectedHour > 23) {
            throw new Error("hour must be 0..23");
        }
        if (!Number.isInteger(selectedInterval) || selectedInterval < 1 || selectedInterval > 23) {
            throw new Error("hour interval must be 1..23");
        }
        if (!["0", "1", "2", "3", "4", "5", "6"].includes(String(selectedDow))) {
            throw new Error("day of week must be 0..6");
        }
        if (!Number.isInteger(selectedDom) || selectedDom < 1 || selectedDom > 31) {
            throw new Error("day of month must be 1..31");
        }

        switch (selectedMode) {
            case "hourly":
                return `${selectedMinute} * * * *`;
            case "every_n_hours":
                return `${selectedMinute} */${selectedInterval} * * *`;
            case "daily":
                return `${selectedMinute} ${selectedHour} * * *`;
            case "weekdays":
                return `${selectedMinute} ${selectedHour} * * 1-5`;
            case "weekly":
                return `${selectedMinute} ${selectedHour} * * ${selectedDow}`;
            case "monthly":
                return `${selectedMinute} ${selectedHour} ${selectedDom} * *`;
            case "custom": {
                const cron = String(custom || "").trim();
                if (cron.split(/\s+/).length !== 5) {
                    throw new Error("custom cron must have 5 fields");
                }
                return cron;
            }
            default:
                throw new Error(`unknown cron mode: ${selectedMode}`);
        }
    }

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        runbookConfig: {
            cronPreview: function (
                mode,
                minute,
                hour,
                interval,
                dow,
                dom,
                custom,
                timezone
            ) {
                try {
                    const cron = buildCron(
                        mode,
                        minute,
                        hour,
                        interval,
                        dow,
                        dom,
                        custom
                    );
                    return `${cron} (${timezone || "UTC"})`;
                } catch (error) {
                    return `Invalid cron: ${error.message || error}`;
                }
            }
        }
    });
})();
