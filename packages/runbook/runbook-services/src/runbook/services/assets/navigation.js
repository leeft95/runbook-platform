(function () {
    "use strict";

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        runbookNavigation: {
            scrollToHash: function (_pathname, hash) {
                const fragment = String(hash || "").replace(/^#/, "");
                if (!fragment) {
                    return window.dash_clientside.no_update;
                }

                let targetId;
                try {
                    targetId = decodeURIComponent(fragment);
                } catch (_error) {
                    return window.dash_clientside.no_update;
                }
                if (!targetId) {
                    return window.dash_clientside.no_update;
                }

                const scrollToTarget = function () {
                    const target = document.getElementById(targetId);
                    if (target) {
                        target.scrollIntoView({block: "start"});
                    }
                };
                window.requestAnimationFrame(function () {
                    scrollToTarget();
                    window.setTimeout(scrollToTarget, 80);
                });
                return "";
            },
        },
    });
})();
