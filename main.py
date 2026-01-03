import csv
import io
import logging
import os
import markdown2
import googlemaps
from geojson import Point, dumps, FeatureCollection, Feature


from flask import (
    Flask,
    request,
    redirect,
    render_template,
    render_template_string,
    url_for,
    session,
)

import firebase_admin
from firebase_admin import firestore
from authlib.integrations.flask_client import OAuth
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key")

# OAuth configuration
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    # This is only needed if using openId to fetch user info
    client_kwargs={'scope': 'openid email profile'},
)

ALLOWED_EMAILS = ['billnapier@gmail.com']


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            return redirect(url_for('login_page'))
        if user.get('email') not in ALLOWED_EMAILS:
            return "Unauthorized", 401
        return f(*args, **kwargs)
    return decorated_function


fb_app = firebase_admin.initialize_app()
db = firestore.client()

googlemaps_config = db.collection('configs').document('googlemaps').get().to_dict()
gmaps = googlemaps.Client(key=googlemaps_config.get('api_key'))

_COMMITTEE_CHAIR = "Committee Chair"
_COR = "Chartered Organization Rep."
_UNIT_LEADER = frozenset(
    ["Cubmaster", "Scoutmaster", "Skipper", "Venturing Crew Advisor"]
)

_COMMITTEE_CHAIR_KEY = "cc"
_COR_KEY = "cor"
_UNIT_LEADER_KEY = "leader"


@app.route("/")
@login_required
def root():
    return render_template("main.html", googlemaps_api_key=googlemaps_config.get('api_key'))


@app.route('/login')
def login():
    google = oauth.create_client('google')
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/login_page')
def login_page():
    return render_template('login.html')


@app.route('/authorize')
def authorize():
    google = oauth.create_client('google')
    token = google.authorize_access_token()
    resp = google.get('userinfo')
    user_info = resp.json()
    # do something with the token and profile
    session['user'] = user_info
    if user_info.get('email') not in ALLOWED_EMAILS:
        return "Unauthorized: Only billnapier@gmail.com is allowed.", 401
    return redirect('/')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))


def UnitNameToUnitType(name):
    return name.split(" ")[0].upper()


def UnitNameToUnitLetter(name):
    return UnitNameToUnitType(name)[0]


def UnitNameToNumber(name):
    num = name.split(" ")[1]
    return str(int(num))


@app.route("/upload_key3", methods=["POST"])
@login_required
def upload_key3():
    logging.warning("%s", request.files)
    if "file" not in request.files:
        return "No file part"
    fp = request.files["file"].stream
    # Skip the first 8 header lines in this report.
    for _ in range(8):
        fp.readline()

    with io.StringIO(fp.read().decode()) as f:
        for row in csv.DictReader(f):
            unit_type = UnitNameToUnitLetter(row["Unit_Name"])
            unit_num = UnitNameToNumber(row["Unit_Name"])
            position = row["Position"]

            key = f"{unit_type} {unit_num}"
            leader = dict(name=row["Name_"], email=row["Email"])

            unit_entry = dict(
                key=key,
                unit_type=UnitNameToUnitType(row["Unit_Name"]),
                unit_num=unit_num,
            )
            if position == _COR:
                unit_entry[_COR_KEY] = leader
            elif position == _COMMITTEE_CHAIR:
                unit_entry[_COMMITTEE_CHAIR_KEY] = leader
            elif position in _UNIT_LEADER:
                unit_entry[_UNIT_LEADER_KEY] = leader
            else:
                logging.error("%s is an unknown leader type", position)

            logging.warning("Storing unit %s", key)
            db.collection("units").document(key).set(unit_entry, merge=True)
    return redirect("/")


@app.route("/upload_pin", methods=["POST"])
@login_required
def upload_pin():
    logging.warning("%s", request.files)
    if "file" not in request.files:
        return "No file part"
    fp = request.files["file"].stream

    with io.StringIO(fp.read().decode()) as f:
        for row in csv.DictReader(f):
            full_unit_name = row["Unit_Name"]
            unit_name = full_unit_name.split(", ")[0]

            unit_type = UnitNameToUnitLetter(unit_name)
            unit_num = UnitNameToNumber(unit_name)

            key = f"{unit_type} {unit_num}"

            address_line = row["Unit_BeAScout_Address"]
            city = row["City"]
            state = row["State"]
            zipcode = row["ZIPCODE"]
            last_modified_date = row["Last_Modified_Date"]

            # Geocoding an address
            geocode_result = gmaps.geocode(f'{address_line}, {city}, {state}')[0]
            location = geocode_result.get('geometry').get('location')

            unit_entry = dict(
                key=key,
                unit_type=UnitNameToUnitType(row["Unit_Name"]),
                unit_num=unit_num,
                pin_info=dict(
                    address_line=address_line,
                    city=city,
                    state=state,
                    zipcode=zipcode,
                    latitude=location.get('lat'),
                    longitude=location.get('lng'),
                    last_modified_date=last_modified_date,
                ),
                website=row["Unit_Website"],
            )

            db.collection("units").document(key).set(unit_entry, merge=True)

            logging.error(unit_name)
    return redirect("/")


def get_contacts_from_unit(unit):
    return [
        contact
        for contact in [unit.get("leader"), unit.get("cor"), unit.get("cc")]
        if contact is not None
    ]


@app.route("/units")
@login_required
def list_units():
    units = [u.to_dict() for u in db.collection("units").stream()]
    all_emails = []
    for unit in units:
        all_emails.extend([c.get("email") for c in get_contacts_from_unit(unit)])

    return render_template("units.html", units=units, all_emails=all_emails)


@app.route("/units/<unit_key>")
@login_required
def list_single_unit(unit_key: str):
    logging.warning(unit_key)
    unit = db.collection("units").document(unit_key).get().to_dict()
    return render_template(
        "single_unit.html",
        unit=unit,
        emails=[c.get("email") for c in get_contacts_from_unit(unit)],
    )


@app.route("/send_email", methods=["POST", "GET"])
@login_required
def send_email():
    unit_type = request.form.get("unit_type", request.args.get("unit_type", "PACK"))
    code = request.form.get("msg", "")
    subject = request.form.get("subject", "")

    units = [
        u.to_dict()
        for u in db.collection("units").where("unit_type", "==", unit_type).stream()
    ]

    markdown = markdown2.markdown(render_template_string(code, unit=units[0]))

    if request.method == "GET" or request.form.get("preview"):
        return render_template(
            "send_email.html",
            markdown=markdown,
            code=code,
            unit_type=unit_type,
            subject=subject,
            units=units,
        )
    elif request.form.get("send"):
        send_to_units(code=code, subject=subject, units=units)
        redirect(url_for("root"))
    else:
        send_to_units(code=code, subject=subject, units=units, send_test=True)
        return render_template(
            "send_email.html",
            markdown=markdown,
            code=code,
            unit_type=unit_type,
            subject=subject,
            units=units,
        )

def _unit_to_geo_feature(unit):
    pin_info=unit.get('pin_info')
    return Feature(geometry=Point((pin_info.get('longitude'), pin_info.get('latitude'))), 
                   properties=dict(name=unit.get('key'),
                                   address_line=f'{pin_info["address_line"]}',
                                   city=f'{pin_info["city"]}',
                                   state=f'{pin_info["state"]}',
                                   zip=f'{pin_info["zipcode"]}',
                                   ))

@app.route("/unit_geojson")
@login_required
def unit_geojson():
    units = [_unit_to_geo_feature(u.to_dict()) for u in db.collection("units").stream()]
    return dumps(FeatureCollection(units))

def send_to_units(code, subject, units, send_test=False):
    for unit in units:
        db.collection("mailqueue").add(
            dict(subject=subject, code=code, unit=unit, send_test=send_test)
        )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
