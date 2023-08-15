import csv
import io
import logging
import os
import markdown2

from flask import Flask, request, redirect, render_template

import firebase_admin
from firebase_admin import firestore

app = Flask(__name__)

fb_app = firebase_admin.initialize_app()
db = firestore.client()

_COMITTEE_CHAIR = 'Committee Chair'
_COR = 'Chartered Organization Rep.'
_UNIT_LEADER = frozenset(
    ['Cubmaster', 'Scoutmaster', 'Skipper', 'Venturing Crew Advisor'])

_COMITTEE_CHAIR_KEY = 'cc'
_COR_KEY = 'cor'
_UNIT_LEADER_KEY = 'leader'


@app.route("/")
def root():
    return render_template('main.html')


def UnitNameToUnitType(name):
    return name.split(' ')[0].upper()


def UnitNameToUnitLetter(name):
    return UnitNameToUnitType(name)[0]


def UnitNameToNumber(name):
    num = name.split(' ')[1]
    return str(int(num))


@app.route("/upload", methods=['POST'])
def upload():
    logging.warning("%s" % request.files)
    if 'file' not in request.files:
        return 'No file part'
    fp = request.files['file'].stream
    # Skip the first 8 header lines in this report.
    for _ in range(8):
        fp.readline()

    with io.StringIO(fp.read().decode()) as f:
        for row in csv.DictReader(f):
            unit_type = UnitNameToUnitLetter(row['Unit_Name'])
            unit_num = UnitNameToNumber(row['Unit_Name'])
            position = row['Position']

            key = '%s %s' % (unit_type, unit_num)
            leader = dict(name=row['Name_'], email=row['Email'])

            unit_entry = dict(key=key, unit_type=UnitNameToUnitType(row['Unit_Name']),
                              unit_num=unit_num)
            if position == _COR:
                unit_entry[_COR_KEY] = leader
            elif position == _COMITTEE_CHAIR:
                unit_entry[_COMITTEE_CHAIR_KEY] = leader
            elif position in _UNIT_LEADER:
                unit_entry[_UNIT_LEADER_KEY] = leader
            else:
                logging.error('%s is an unknow leader type' % position)

            logging.warning('Storing unit %s', key)
            db.collection('units').document(key).set(unit_entry, merge=True)
    return redirect('/')


def get_contacts_from_unit(unit):
    return [contact for contact in [unit.get('leader'), unit.get('cor'), unit.get('cc')] if contact is not None]


@app.route('/units')
def list_units():
    units = [u.to_dict() for u in db.collection('units').stream()]
    all_emails = []
    for unit in units:
        all_emails.extend([c.get('email')
                          for c in get_contacts_from_unit(unit)])

    return render_template('units.html', units=units, all_emails=all_emails)


@app.route('/units/<unit_key>')
def list_single_unit(unit_key: str):
    logging.warning(unit_key)
    unit = db.collection('units').document(unit_key).get().to_dict()
    return render_template('single_unit.html',
                           unit=unit,
                           emails=[c.get('email') for c in get_contacts_from_unit(unit)])


@app.route('/testing', methods=['POST', 'GET'])
def testing():
    if request.method == 'GET' or request.form.get('preview'):
        code = request.form.get('msg')
        if code:
            markdown = markdown2.markdown(code)
        else:
            markdown = ''
        return f"""
        <HTML><BODY>
            %s
            <form enctype="multipart/form-data" action="/testing" method="POST">
            <label for="msg">msg:</label><br>

                <textarea id="msg" name="msg" rows="50" cols="50">%s</textarea>
                <br>
                <input type="submit" value="Preview" name="preview" /><br>
                <input type="submit" value="Send" name="send"/>
            </form>
        </BODY></HTML>
        """ % (markdown, code)
    else:
        return markdown2.markdown("*SEND*")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
