import dash_bootstrap_components as dbc

from dash import html

def create_card(title, id, icon_class):
    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(
                    [
                        html.I(className=f"fa {icon_class}", style={"font-size": "2rem"}),
                        html.H5(title),
                    ],
                    className="d-flex justify-content-between align-items-center",
                ),
            ]
        ),
        id=id,
        className="card-style",
    )
