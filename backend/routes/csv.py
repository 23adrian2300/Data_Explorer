from flask import Blueprint, request, redirect, flash, url_for, send_from_directory
from prisma.models import CSVFile
from prisma import Prisma, register
from werkzeug.utils import secure_filename
import os
import uuid
import csv
import shutil

csv_route = Blueprint('csv', __name__)
STORAGE_CSV = '.\static'
db = Prisma()
register(db)
ALLOWED_EXTENSIONS = {'csv'}
csvs = {}

"""
Do zrobienia + poprawa poprzednich aby działały w polaczeniu z frontem
/csv/{user}/{id}/data/{zmienna} - PUT update zmiennej do podanej, zwraca nową zmienną  
/csv/{user}/{id}/data/{zmienna}/updateDetail - POST ustawia puste na określoną rzecz z szczegółów np. mediana średnia itp (to co będzie w details[name] 
/csv/files/{userId}/{id}/img/{img} - GET wszystkie wykresy itp
/csv/files/{userId}/{id}/csv/{img} - GET wszystkie csv'ki
"""

def is_float(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def handle_csv(fileId, path, filename):
    with open(path, 'r', encoding="utf8") as csv_file:
        reader = csv.reader(csv_file)
        data = {}
        dataKeys = []
        for i, row in enumerate(reader):
            rowArr = row[0].split(';')
            if i == 0:
                data = {key: [] for key in rowArr}
                dataKeys = rowArr
            else:
                for j, key in enumerate(rowArr):
                    data[dataKeys[j]].append({
                        "value": key,
                        "type": "normal" if key is not None else "null"
                    })
        print(data)
        csvs[fileId] = {
            "cols": [{
                "name": key,
                "type": "number" if all(
                    value['value'].isnumeric() or is_float(value['value']) or value['value'] == '' for value in
                    data[key]) else "string",
                "values": data[key]
            } for key in data],
            "name": filename,
            "id:": fileId
        }
        print(csvs)
        # csvs[fileId] = data


@csv_route.route('/csv', methods=['POST'])
async def upload_csv():
    print(request.headers)
    if 'file' not in request.files or 'userId' not in request.form:
        return {"error": "No file part or no user id provided"}, 400
    else:
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_fileid = str(uuid.uuid4())
            path = os.path.join(STORAGE_CSV, request.form['userId'], unique_fileid)
            os.makedirs(path, exist_ok=True)
            file.save(os.path.join(path, filename))
            shutil.copy(os.path.join(path, filename), os.path.join(path, filename.strip('.csv') + "_original" + ".csv"))
            try:
                await db.connect()
                await CSVFile.prisma().delete_many(
                    where={"userId": request.form['userId']}
                )
                csv_file = await CSVFile.prisma().create(
                    data={
                        "userId": request.form['userId'],
                        "name": filename,
                        "path": os.path.join(path, filename),
                    }
                )

                returnObject = {
                    "message": "File uploaded",
                    "fileId": unique_fileid
                }
                handle_csv(unique_fileid, os.path.join(path, filename), filename)

                return returnObject, 200
            finally:
                await db.disconnect()

            # return {"message": "File uploaded", "fileId": str(unique_fileid)}, 200


@csv_route.route('/csv/<fileId>', methods=['GET'])
async def get_csv(fileId):  # one csv
    try:
        # await db.connect()
        # csv_file = await CSVFile.prisma().find_unique(
        #     where={"fileId": fileId}
        # )
        # print(csv_file)
        return csvs[fileId]

    finally:
        await db.disconnect()


@csv_route.route('/csv/<fileId>/data/<columnName>', methods=['GET'])
async def get_column(fileId, columnName):
    try:
        for column in csvs[fileId]["cols"]:
            if column["name"] == columnName:
                return column
        return {"error": "Column not found"}, 400
    except Exception as e:
        return {"error": str(e)}, 400
    finally:
        await db.disconnect()


@csv_route.route('/csv/<fileId>/fix/fixcols', methods=['POST'])
async def fix_cols(userId, fileId):
    try:
        empty_columns = []
        cols = csvs[fileId]["cols"]
        print(cols)
        for column in cols:
            if all(value["value"] == "" for value in column["values"]):
                empty_columns.append(column)
        for column in empty_columns:
            cols.remove(column)
        return csvs[fileId]
    except Exception as e:
        return {"error": str(e)}, 400


@csv_route.route('/csv/<fileId>/fix/fixrows', methods=['POST'])
async def fix_rows(userId, fileId):
    try:
        empty_rows = []
        cols = csvs[fileId]["cols"]
        i_max = 0
        for column in cols:
            empty_rows.append([])
            i = 0
            for value in column["values"]:
                if value["value"] == "":
                    empty_rows[-1].append(i)
                i += 1
            if i > i_max:
                i_max = i
        for i in range(i_max):
            flag = True
            for table in empty_rows:
                if i not in table:
                    flag = False
            if flag:
                for column in cols:
                    column["values"].pop(i)
        return csvs[fileId]
    except Exception as e:
        return {"error": str(e)}, 400



@csv_route.route('/csv/<fileId>', methods=['PUT'])
async def update_csv(userId, fileId):
    try:
        if 'file' not in request.files:
            return {"error": "No file part"}, 400
        else:
            file = request.files['file']
            if file.filename == '':
                return {"error": "No selected file"}, 400
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                path = os.path.join(STORAGE_CSV, userId, fileId)
                file.save(os.path.join(path, filename))
                handle_csv(fileId, os.path.join(path, filename), filename)
                return {"message": "File updated"}, 200
    except Exception as e:
        return {"error": str(e)}, 400


@csv_route.route('/csv/<fileId>/<columnName>/updateConst', methods=['POST'])
async def update_const(userId, fileId, columnName):
    try:
        for column in csvs[fileId]["cols"]:
            if column["name"] == columnName:
                if column['type'] == "number":
                    const = request.json["value"]
                    for value in column["values"]:
                        if value["value"] == "":
                            value["value"] = const

                    return csvs[fileId]

    except Exception as e:
        return {"error, column not exist": str(e)}, 400

    # `${address}/files/${title}/fixes/${col}/average`


@csv_route.route('/csv//<fileId>/<columnName>/updateMedian', methods=['POST'])
async def update_median(userId, fileId, columnName):
    try:
        for column in csvs[fileId]["cols"]:
            if column["name"] == columnName:
                if column['type'] == "number":
                    values = [float(value["value"]) for value in column["values"] if value["value"] != ""]
                    values.sort()
                    median = values[len(values) // 2]
                    for value in column["values"]:
                        if value["value"] == "":
                            value["value"] = median

                    return csvs[fileId]

    except Exception as e:
        return {"error, column not exist": str(e)}, 400


@csv_route.route('/csv/<userId>/<fileId>/data/<columnName>/updateMostCommon', methods=['POST'])
async def update_most_common(userId, fileId, columnName):
    try:
        for column in csvs[fileId]["cols"]:
            if column["name"] == columnName:
                values = [(value["value"]) for value in column["values"] if value["value"] != ""]
                most_common = ""
                for i in range(len(values)):
                    if values.count(values[i]) > values.count(most_common):
                        most_common = values[i]
                for value in column["values"]:
                    if value["value"] == "":
                        value["value"] = most_common
                return csvs[fileId]

    except Exception as e:
        return {"error, column not exist": str(e)}, 400


@csv_route.route('/csv/<fileId>/fixes/<columnName>/upadateAverage', methods=['POST'])
async def update_avg(userId, fileId, columnName):
    try:
        for column in csvs[fileId]["cols"]:
            if column["name"] == columnName:
                if column['type'] == "number":
                    values = [float(value["value"]) for value in column["values"] if value["value"] != ""]
                    print(values)
                    avg = sum(values) / len(values)
                    avg = round(avg, 2)
                    for value in column["values"]:
                        if value["value"] == "":
                            value["value"] = str(avg)

                    return csvs[fileId]
                else:
                    return {"error": "Column is not a number type"}, 400
    except Exception as e:
        return {"error, columnd not exist": str(e)}, 400
