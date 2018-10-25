import numpy as np
import os
import tifffile
import xarray as xr

from bokeh.io import curdoc
from bokeh.layouts import row, widgetbox
from bokeh.models import (
    ColumnDataSource, )
from bokeh.models.widgets import (
    Button,
    Paragraph,
    Select,
    Slider,
    TextInput,
    Toggle,
)
from figures.image_plot import create_image_figure
from figures.roi_plot import create_roi_figure

base_dir_input = TextInput(value='Enter path...', title='Base Directory')
IMAGE_EXT = '.tif'


def get_file_paths(ext: str = IMAGE_EXT) -> list:
    """
    Returns a list of files ending with 'ext' within a directory tree.
    
    :param ext: The target file extension, defaults to IMAGE_EXT.
    :type ext: str
    :return: A list of file paths.
    :rtype: list
    """
    image_paths = []
    for root, dirs, files in os.walk(base_dir_input.value):
        for f in files:
            if f.endswith(ext):
                image_paths.append(os.path.join(root, f))
    return image_paths


def update_image_select(attr, old, new):
    if os.path.isdir(new):
        image_paths = get_file_paths()
        relative_paths = [path[len(new):] for path in image_paths]
        if relative_paths:
            image_select.options = relative_paths
            image_select.value = image_select.options[0]
            return
    image_select.options = ['---']


def get_db_path() -> str:
    if os.path.isdir(base_dir_input.value):
        return os.path.join(base_dir_input.value, 'db.nc')


def read_db() -> xr.Dataset:
    try:
        return xr.open_dataset(get_db_path())
    except FileNotFoundError:
        return xr.Dataset()


base_dir_input.on_change('value', update_image_select)

raw_source = ColumnDataSource(data=dict(image=[], meta=[]))

image_select = Select(title='Image', value='---', options=['---'])


def get_full_path(relative_path: str) -> str:
    image_paths = get_file_paths()
    try:
        return [f for f in image_paths if f.endswith(relative_path)][0]
    except IndexError:
        print('Failed to find appropriate image path')


def get_current_file_path() -> str:
    return get_full_path(image_select.value)


def get_current_file_name() -> str:
    return os.path.basename(image_select.value).split('.')[0]


def get_current_metset_path() -> str:
    location = os.path.dirname(get_current_file_path())
    return os.path.join(location, get_current_file_name() + '.nc')


def read_image_file(path: str) -> np.ndarray:
    with tifffile.TiffFile(path, movie=True) as f:
        try:
            data = f.asarray(slice(1, None, 2))  # read the second channel only
        except ValueError:
            data = f.asarray()
        return data


def get_current_image() -> np.ndarray:
    return raw_source.data['image'][0]


def get_current_metadata() -> dict:
    try:
        return raw_source.data['meta'][0]
    except IndexError:
        return None


def update_time_slider() -> None:
    image = get_current_image()
    if len(image.shape) is 3:
        time_slider.end = image.shape[0] - 1
        time_slider.disabled = False
    else:
        time_slider.end = 1
        time_slider.disabled = True
    time_slider.value = 0


def get_current_frame() -> np.ndarray:
    image = get_current_image()
    if len(image.shape) is 3:
        return image[time_slider.value, :, :]
    return image


def update_plot_axes(width: int, height: int) -> None:
    plot.x_range.end = width
    plot.y_range.end = height


def draw_existing_rois(db: xr.Dataset) -> None:
    path = get_full_path(image_select.value)
    if type(db['path'].values.tolist()) is not str:
        roi_data = np.asarray(db['roi_data'].loc[{
            'path': path
        }].values.tolist())
    else:
        roi_data = np.asarray(db['roi_data'].values.tolist())
    roi_data = roi_data[~np.isnan(roi_data).any(axis=1)]
    x = []
    y = []
    width = []
    height = []
    for roi in roi_data:
        x.append(roi[0])
        y.append(roi[1])
        width.append(roi[2])
        height.append(roi[3])
    roi_source.data = dict(x=x, y=y, width=width, height=height)


def draw_existing_vectors(db: xr.Dataset) -> None:
    path = get_full_path(image_select.value)
    if type(db['path'].values.tolist()) is not str:
        vector_data = np.asarray(db['vector_data'].loc[{
            'path': path
        }].values.tolist())
    else:
        vector_data = np.asarray(db['vector_data'].values.tolist())
    vector_data = vector_data[~np.isnan(vector_data).any(axis=1)]
    xs = []
    ys = []
    for vector in vector_data:
        xs.append([vector[0], vector[1]])
        ys.append([vector[2], vector[3]])
    vector_source.data = dict(xs=xs, ys=ys)


def update_plot() -> None:
    frame = get_current_frame()
    width, height = frame.shape[1], frame.shape[0]
    image_source.data = dict(image=[frame], dw=[width], dh=[height])
    update_plot_axes(width, height)
    path = get_full_path(image_select.value)
    db_path = get_db_path()
    if os.path.isfile(db_path):
        with xr.open_dataset(db_path) as db:
            if 'path' in db and path in db['path'].values:
                draw_existing_rois(db)
                draw_existing_vectors(db)
                return
    roi_source.data = dict(x=[], y=[], width=[], height=[])
    vector_source.data = dict(xs=[], ys=[])


def read_metadata(path: str) -> dict:
    with tifffile.TiffFile(path, movie=True) as f:
        return f.scanimage_metadata


def get_frame_rate() -> float:
    meta = get_current_metadata()
    if meta:
        return meta['FrameData']['SI.hRoiManager.scanFrameRate']


def get_line_rate() -> float:
    meta = get_current_metadata()
    if meta:
        line_period = meta['FrameData']['SI.hRoiManager.linePeriod']
        return 1 / line_period


def get_number_of_rows() -> float:
    meta = get_current_metadata()
    if meta:
        return meta['FrameData']['SI.hRoiManager.linesPerFrame']


def get_number_of_columns() -> float:
    meta = get_current_metadata()
    if meta:
        return meta['FrameData']['SI.hRoiManager.pixelsPerLine']


def get_fov() -> float:
    try:
        return int(fov_input.value)
    except ValueError:
        print('Invalid input! FOV must be an integer.')


def get_zoom_factor() -> float:
    meta = get_current_metadata()
    if meta:
        return meta['FrameData']['SI.hRoiManager.scanZoomFactor']


def calc_x_pixel_to_micron() -> float:
    try:
        return get_number_of_columns() / (get_fov() * get_zoom_factor())
    except TypeError:
        pass


def calc_y_pixel_to_micron() -> float:
    try:
        return get_number_of_rows() / (get_fov() * get_zoom_factor())
    except TypeError:
        pass


PARAM_GETTERS = {
    'zoom_factor': get_zoom_factor,
    'n_rows': get_number_of_rows,
    'n_columns': get_number_of_columns,
    'frame_rate': get_frame_rate,
    'line_rate': get_line_rate,
    'x_pixel_to_micron': calc_x_pixel_to_micron,
    'y_pixel_to_micron': calc_y_pixel_to_micron,
}


def get_string(param: str):
    try:
        value = PARAM_GETTERS[param]()
        if value:
            return str(value)
    except KeyError:
        return 'INVALID'
    return '---'


def update_parameter_widgets() -> None:
    line_rate_input.value = get_string('line_rate')
    frame_rate_input.value = get_string('frame_rate')
    rows_input.value = get_string('n_rows')
    columns_input.value = get_string('n_columns')
    zoom_factor_input.value = get_string('zoom_factor')
    x_pixel_to_micron_input.value = get_string('x_pixel_to_micron')
    y_pixel_to_micron_input.value = get_string('y_pixel_to_micron')


def select_image(attr, old, new):
    message_paragraph.style = {'color': 'orange'}
    message_paragraph.text = 'Loading...'
    path = get_full_path(new)
    raw_source.data = {
        'image': [read_image_file(path)],
        'meta': [read_metadata(path)]
    }
    update_time_slider()
    update_plot()
    update_parameter_widgets()
    message_paragraph.style = {'color': 'green'}
    message_paragraph.text = 'Image successfully loaded!'


image_select.on_change('value', select_image)

time_slider = Slider(start=0, end=1, value=0, step=1, title='Time')


def update_frame(attr, old, new):
    image = get_current_image()
    if len(image.shape) is 3:
        try:
            image_source.data['image'] = [image[new, :, :]]
            if roi_source.selected.indices:
                roi_plot_source.data['image'] = [
                    get_roi_data(roi_source.selected.indices[0],
                                 time_slider.value)
                ]
        except IndexError:
            print('Failed to update image frame!')


def calculate_2d_projection() -> np.ndarray:
    image = get_current_image()
    if len(image.shape) is 3:
        return np.max(image, axis=0)


time_slider.on_change('value', update_frame)

image_source = ColumnDataSource(
    data=dict(
        image=[],
        x=[],
        y=[],
        dw=[],
        dh=[],
    ))

roi_source = ColumnDataSource(data={
    'x': [],
    'y': [],
    'width': [],
    'height': [],
})

roi_plot_source = ColumnDataSource(data=dict(image=[], dw=[], dh=[]))

roi_plot = create_roi_figure(roi_plot_source)


def change_selected_roi(attr, old, new):
    if new:
        roi_index = new.indices[0]
        roi_data = get_roi_data(roi_index, time_slider.value)
        roi_plot_source.data = dict(
            image=[roi_data], dw=[roi_data.shape[1]], dh=[roi_data.shape[0]])
        roi_plot.height = roi_data.shape[0] * 3
        roi_plot.width = roi_data.shape[1] * 3
        roi_plot.x_range.end = roi_data.shape[1]
        roi_plot.y_range.end = roi_data.shape[0]


roi_source.on_change('selected', change_selected_roi)


def get_roi_data(roi_index: int, frame: int):
    width = round(roi_source.data['width'][roi_index])
    height = round(roi_source.data['height'][roi_index])
    x_center = round(roi_source.data['x'][roi_index])
    y_center = round(roi_source.data['y'][roi_index])
    x_start = x_center - width // 2
    x_end = x_center + width // 2
    y_start = y_center - height // 2
    y_end = y_center + height // 2
    return get_current_image()[frame, y_start:y_end, x_start:x_end]


vector_source = ColumnDataSource(data={
    'xs': [],
    'ys': [],
})

plot = create_image_figure(image_source, roi_source, vector_source)

save_button = Button(label='Save', button_type="success")

toggle_2d = Toggle(label='2D Projection')


def show_2d_projection(attr, old, new):
    if new is False:
        time_slider.disabled = False
        update_plot()
    else:
        time_slider.disabled = True
        image_source.data['image'] = [calculate_2d_projection()]


toggle_2d.on_change('active', show_2d_projection)

fov_input = TextInput(value='870', title='FOV (μm)')


def update_pixel_to_micron(attr, old, new):
    x_pixel_to_micron_input.value = str(calc_x_pixel_to_micron())
    y_pixel_to_micron_input.value = str(calc_y_pixel_to_micron())


fov_input.on_change('value', update_pixel_to_micron)

zoom_factor_input = TextInput(value='---', title='Zoom Factor')
zoom_factor_input.disabled = True
columns_input = TextInput(value='---', title='Columns')
columns_input.disabled = True
rows_input = TextInput(value='---', title='Rows')
rows_input.disabled = True
x_pixel_to_micron_input = TextInput(value='---', title='Pixel to Micron (X)')
x_pixel_to_micron_input.disabled = True
y_pixel_to_micron_input = TextInput(value='---', title='Pixel to Micron (Y)')
y_pixel_to_micron_input.disabled = True
line_rate_input = TextInput(value='---', title='Line Rate')
frame_rate_input = TextInput(value='---', title='Frame Rate')

run_flics_button = Button(label='Run FLICS', button_type='primary')

message_paragraph = Paragraph(text='')


def get_roi_params(index: int) -> list:
    values = roi_source.data
    return [
        values['x'][index],
        values['y'][index],
        values['width'][index],
        values['height'][index],
    ]


def get_vector_params(index: int) -> list:
    values = vector_source.data
    return [
        values['xs'][index][0],
        values['xs'][index][1],
        values['ys'][index][0],
        values['ys'][index][1],
    ]


def get_roi_data_by_index() -> np.ndarray:
    roi_data = np.full((50, 4), np.nan)
    n_rois = len(roi_source.data['x'])
    for index in range(n_rois):
        roi_data[index, :] = get_roi_params(index)
    return roi_data


def get_vector_data_by_index() -> np.ndarray:
    vector_data = np.full((50, 4), np.nan)
    n_vectors = len(vector_source.data['xs'])
    for index in range(n_vectors):
        vector_data[index, :] = get_vector_params(index)
    return vector_data


def create_data_dict() -> dict:
    return {
        '2d_projection': (['x', 'y'], calculate_2d_projection()),
        'line_rate': float(line_rate_input.value),
        'frame_rate': float(frame_rate_input.value),
        'roi_data': (['roi_num', 'roi_loc'], get_roi_data_by_index()),
        'vector_data': (['vector_num', 'vector_loc'],
                        get_vector_data_by_index()),
        'corr_calc_state': 0,
        'fitting_state': 0,
    }


def create_coords_dict(path: str) -> dict:
    image = get_current_image()
    return {
        'path': path,
        'pix_x': np.arange(image.shape[2]),
        'pix_y': np.arange(image.shape[1]),
        'time': np.arange(image.shape[0]),
        'roi_num': np.arange(50, dtype=np.uint8),
        'roi_loc': ['x', 'y', 'width', 'height'],
        'vector_num': np.arange(50, dtype=np.uint8),
        'vector_loc': ['x_start', 'x_end', 'y_start', 'y_end'],
    }


def save():
    path = get_full_path(image_select.value)
    data_vars = create_data_dict()
    db_path = get_db_path()
    if os.path.isfile(db_path):
        with xr.open_dataset(db_path) as db:
            if path in db['path'].values:
                print('trying to update DB for existing path')
                for key, value in data_vars.items():
                    if type(db['path'].values.tolist()) is not str:
                        if db[key].loc[{
                                'path': path
                        }].values.tolist() != value:
                            db[key].loc[{'path': path}] = value
                    else:
                        if db[key].values.tolist() != value:
                            db[key] = value
            else:
                print('trying to update DB with new path')
                coords = create_coords_dict(path)
                ds = xr.Dataset(data_vars, coords)
                db = xr.concat([db, ds], dim='path')
            os.remove(db_path)
            db.to_netcdf(get_db_path(), mode='w')
    else:
        coords = create_coords_dict(path)
        db = xr.Dataset(data_vars, coords)
        db.to_netcdf(db_path)


save_button.on_click(save)

main_layout = row(
    widgetbox(
        base_dir_input,
        image_select,
        message_paragraph,
        time_slider,
        rows_input,
        columns_input,
        zoom_factor_input,
        x_pixel_to_micron_input,
        y_pixel_to_micron_input,
        fov_input,
        line_rate_input,
        frame_rate_input,
        toggle_2d,
        save_button,
        run_flics_button,
    ),
    plot,
    roi_plot,
    name='main_layout',
)

curdoc().add_root(main_layout)
