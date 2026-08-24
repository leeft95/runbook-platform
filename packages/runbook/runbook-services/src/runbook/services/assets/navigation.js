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

                const waitForTarget = function () {
                    let observer;
                    let timeoutId;
                    const cleanup = function () {
                        if (observer) {
                            observer.disconnect();
                        }
                        if (timeoutId) {
                            window.clearTimeout(timeoutId);
                        }
                    };
                    const scrollToTarget = function () {
                        const target = document.getElementById(targetId);
                        if (!target) {
                            return false;
                        }
                        target.scrollIntoView({block: "start"});
                        cleanup();
                        return true;
                    };

                    if (scrollToTarget()) {
                        return;
                    }
                    observer = new MutationObserver(scrollToTarget);
                    observer.observe(document.body, {childList: true, subtree: true});
                    timeoutId = window.setTimeout(cleanup, 2000);
                };
                window.requestAnimationFrame(waitForTarget);
                return "";
            },
        },
    });
})();
