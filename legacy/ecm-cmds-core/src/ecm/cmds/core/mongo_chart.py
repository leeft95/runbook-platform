from __future__ import annotations

import ecm.cmds.pyg as pyg
from pyg_cell import periodic_cell


class MongoChartStore(object):
    """
    Saving and loading plotly charts and html tables in mongodb
    """

    def __init__(self):
        self.db = pyg.reports_db()

    def save(self, name, data, df=None, func=None, args=None, tags=None, des=None, collection="chart"):
        self._save_chart(name=name, data=data, df=df, func=func, args=args, tags=tags, des=des, collection=collection)

    def _save_chart(self, name, data, df=None, func=None, args=None, tags=None, des=None, collection="chart"):
        try:
            c = pyg.get_cell(self.db[collection], name=name)
            c.data = data
            if df is not None and c.df != df:
                c.df = df
            if func is not None and c.function != func:
                c.function = func
            if args is not None and c.args != args:
                c.args = args
            if tags is not None and c.tags != tags:
                c.tags = tags
            if des is not None and c.des != des:
                c.des = des
        except Exception:
            c = periodic_cell(db=self.db[collection], name=name, data=data, df=df, function=func, args=args, tags=tags, des=des)
            c.period = "5n"
        c.go()

    def create(self, name, data, df=None, func=None, args=None, tags=None, des=None, collection="chart"):
        try:
            c = pyg.get_cell(self.db[collection], name=name)
            self.db(table=collection)().inc(_id=c._id).drop()
        except Exception:
            c = periodic_cell(db=self.db[collection], name=name, data=data, df=df, function=func, args=args, tags=tags, des=des)
            c.period = "5n"
        c.go()

    def delete(self, name, collection="chart"):
        try:
            c = pyg.get_cell(self.db[collection], name=name)
            self.db(table=collection)().inc(_id=c._id).drop()
            c.go()
        except Exception:
            pass


if __name__ == "__main__":
    pass
