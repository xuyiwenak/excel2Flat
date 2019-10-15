import xlrd
import sys
import os
from common import utils, const

__support_datatypes = ['string', 'int', 'float', 'byte','bool']
# 直接做替换用的字符串
__replace_dict = {"boolean": "bool",
                  "String": "string",
                  "int[]": "string",
                  }
__excel_extension = 'xlsx'


bytes_root_path = os.path.join(os.getcwd(), 'generated_bytes')
excel_root_path = os.path.join(os.getcwd(), 'excel')


def __get_assign_code(mod_name, field_name, field_value, field_type, index):
    if field_type == 'string':
        value_code = "{}{}".format(field_name, index)
        # 只改变首字母大写
        value_code = value_code[0].upper()+value_code[1:]
    else:
        value_code = field_value or 0
    code = "{ModName}.{ModName}Add{FieldName}(builder, {ValueCode})".format(
        ModName = mod_name, FieldName = field_name, ValueCode = value_code)
    print(value_code)
    return code


def __get_single_data_code(mod_name, row_data, index):
    code = \
    """{VariableCreate}
{ModName}.{ModName}Start(builder)
{AssignCode}
single_data{Index} = {ModName}.{ModName}End(builder)"""

    variable_create_code = ''
    for field in row_data:
        field['field_name'] = field['field_name'][0].upper() + field['field_name'][1:]
        if field['field_type'] == 'string':
            variable_create_code += """{}{} = builder.CreateString("{}")""".format(field['field_name'], index, field['field_value'])
            variable_create_code += '\n'
    assign_code = ''
    for field in row_data:
        assign_code += __get_assign_code(
                                            mod_name,
                                            field['field_name'],
                                            field['field_value'],
                                            field['field_type'],
                                            index
                                        )
        assign_code += '\n'
    assign_code = assign_code[:-1]
    code = code.format(VariableCreate = variable_create_code, ModName = mod_name, AssignCode = assign_code, Index = index)
    return code

def __get_list_data_code(mod_name, single_mod_name, list_data):
    row_count = len(list_data)
    all_assign_code = ''
    index = 0
    for row_data in list_data:
        all_assign_code += __get_single_data_code(single_mod_name, row_data, index)
        index += 1
        all_assign_code += '\n'
    offset_code = ''
    for index in range(0, row_count):
        data_name = "single_data{}".format(index)
        offset_code += "builder.PrependUOffsetTRelative({})".format(data_name)
        offset_code += '\n'
    code = \
"""
import generated_python.{SingleModName} as {SingleModName}
import generated_python.{ModName} as {ModName}
import flatbuffers

builder = flatbuffers.Builder(1)

{AllAssignCode}
{ModName}.{ModName}StartDatalistVector(builder, {DataCount})
{OffsetCode}
data_array = builder.EndVector({DataCount})

{ModName}.{ModName}Start(builder)
{ModName}.{ModName}AddDatalist(builder, data_array)
final_data = {ModName}.{ModName}End(builder)
builder.Finish(final_data)
buf = builder.Output()
""".format(
        SingleModName = single_mod_name,
        ModName = mod_name,
        AllAssignCode = all_assign_code,
        DataCount = row_count,
        OffsetCode = offset_code
    )
    return code

def __generate_bytes(mod_name, single_mod_name, bytes_file_root_path, excel_row_list):
    list_code = __get_list_data_code(mod_name, single_mod_name, excel_row_list)
    #print(list_code)
    byte_file_path = os.path.join(bytes_file_root_path, "{}.bytes".format(mod_name))
    byte_file_path = byte_file_path.replace('\\', '/')
    code = """
{ListCode}

with open('{ByteFilePath}', 'wb') as f:
    f.write(buf)
""".format(ListCode = list_code, ByteFilePath = byte_file_path)
    #print(code)
    exec(code)
    print('生成: ', byte_file_path)


# Bytes 生成代码
# ================================== Excel 数据读取 ==================================

def __get_real_value(data_type, raw_value):
    #print('data_type: ', data_type, 'raw_value:', raw_value)
    if data_type == 'string':
        return str(raw_value or "")
    elif data_type == 'int':
        return int(raw_value or 0)
    elif data_type == 'float':
        return float(raw_value or 0.0)
    else:
        return None


def __read_excel_sheet(sheet):
    variable_dict = {}
    sheet_name = sheet.name
    if sheet_name.find("|") != -1:
        sheet_name = sheet_name.split("|")[1]
    mod_name = sheet_name
    single_mod_name = sheet_name + 'RowData'
    data_type_list = sheet.row(1)
    field_name_list = sheet.row(2)
    if not utils.__checkRowHeaderLength(sheet, 4):
        print('表头长度各列不一致, 仔细检查')
        print('异常退出')
        sys.exit()
    for i in range(len(field_name_list)):
        variable_name = field_name_list[i].value
        # 这里需要类型转换
        data_type = data_type_list[i].value
        if not data_type:
            continue
        if variable_name in variable_dict:
            print('存在相同的字段名: ', variable_name)
            print('异常退出')
            sys.exit()
        # 如果是可替换的数据类型
        if __replace_dict.get(data_type):
            data_type = __replace_dict[data_type]
        if not data_type in __support_datatypes:
            print('字段', variable_name, '的数据类型', data_type, '不在支持的列表中')
            print('异常退出')
            sys.exit()
        variable_dict[variable_name] = data_type
    # print(variable_name, data_type, data_type in __support_datatypes)
    # 组合变量定义代码字符串
    data_row_count = sheet.nrows
    sheet_row_data_list = []
    for x in range(const.header_length, data_row_count):
        row_data = sheet.row(x)
        # 存储每一个字段的字段名，数值，类型
        single_row_data = []
        index = 0
        for variable_name in variable_dict:
            #print(variable_name)
            variable_type = variable_dict[variable_name]
            variable_value = __get_real_value(variable_type, row_data[index].value)
            # print(variable_name, variable_type, variable_value)
            index += 1
            data_dict = {
                'field_name': variable_name,
                'field_value': variable_value,
                'field_type': variable_type
            }
            single_row_data.append(data_dict)
        sheet_row_data_list.append(single_row_data)
    __generate_bytes(mod_name, single_mod_name, bytes_root_path, sheet_row_data_list)


def __generate_excel_data(excel_path):
    wb = xlrd.open_workbook(excel_path)
    sheet_count = len(wb.sheet_names())
    sheet1 = wb.sheet_by_index(0)
    for x in range(0, sheet_count):
        sheet = wb.sheet_by_index(x)
        __read_excel_sheet(sheet)


def __generate_all_excel_byte_data():
    for root, dirs, files in os.walk(excel_root_path):
        for file in files:
            excel_file_path = os.path.join(root, file)
            if excel_file_path.endswith(__excel_extension) and not file.startswith('~'):
                __generate_excel_data(excel_file_path)

def run():
    print('---------------- 将excel生成flatbuffers二进制数据 ----------------')
    __generate_all_excel_byte_data()