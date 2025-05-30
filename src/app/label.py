from PIL import Image, ImageDraw, ImageFont
from brother_ql.labels import LabelsManager, FormFactor
from brother_ql import BrotherQLRaster
from brother_ql.brother_ql_create import create_label
from brother_ql.backends import backend_factory
from io import BytesIO
import base64
from . import font, backend, logger, config
import qrcode
from .halftone import halftone
from pprint import pprint


class Label:
    def __init__(self, data, file=False):
        """ creates a new label with the given settings """
        self.size = data['label_size']
        logger.debug('Label size: {}'.format(LabelsManager()[self.size].dots_printable))
        self.width, self.height = LabelsManager()[self.size].dots_printable
        if data['orientation'] != 'rotated':
            self.rotated = True
        else:
            self.rotated = False

        self.data = data
        try:
            self.data['margin_left'] = int(self.data['margin_left'])
        except (KeyError, ValueError):
            self.data['margin_left'] = config['label']['margins']['left']
        try:
            self.data['margin_right'] = int(self.data['margin_right'])
        except (KeyError, ValueError):
            self.data['margin_right'] = config['label']['margins']['right']
        try:
            self.data['margin_top'] = int(self.data['margin_top'])
        except (KeyError, ValueError):
            self.data['margin_top'] = config['label']['margins']['top']
        try:
            self.data['margin_bottom'] = int(self.data['margin_bottom'])
        except (KeyError, ValueError):
            self.data['margin_bottom'] = config['label']['margins']['bottom']
        logger.debug('margin_left: {}'.format(self.data["margin_left"]))
        logger.debug('margin_right: {}'.format(self.data["margin_right"]))
        logger.debug('margin_top: {}'.format(self.data["margin_top"]))
        logger.debug('margin_bottom: {}'.format(self.data["margin_bottom"]))

        self.image = Image.new('L', (self.width, self.height), 255)
        self.label = ImageDraw.Draw(self.image)
        logger.debug('Rotated: {}'.format(self.rotated))

        if 'text' in self.data:
            try:
                self.data['font_spacing'] = int(self.data['font_spacing'])
            except ValueError:
                self.data['font_spacing'] = config['font_spacing']
            self.font_path = font.fonts[data['font_name']]
            self.font_size = data['font_size']
            self.font = ImageFont.truetype(font.fonts[data['font_name']]['path'], int(data['font_size']))
            self.text()
        if 'qr_text' in self.data:
            self.qr()
        if file:
            self.img(file)

    def convert_to_png(self):
        img_buf = BytesIO()
        self.image.save(img_buf, format="PNG")
        img_buf.seek(0)
        return base64.b64encode(img_buf.getbuffer())

    def scale(self, dim):
        img_height, img_width = dim

        # set width and height
        if self.height == 0:
            label_height = dim[0]
        else:
            label_height = self.height
        label_width = self.width

        if self.rotated:
            if img_width > label_height or img_height > label_width:
                ratio = min(label_height / img_width, label_width / img_height)
                x = ratio * img_width
                y = ratio * img_height
            else:
                y = img_width
                x = img_height

        else:
            if img_width > label_width or img_height > label_height:
                ratio = min(label_width / img_width, label_height / img_height)
                x = ratio * img_width
                y = ratio * img_height
            else:
                x = img_width
                y = img_height

        ret = (int(y), int(x))

        logger.debug('Scaled image: {}'.format(ret))

        return ret

    def img(self, img):
        img = Image.open(img)
        logger.debug('Generating label from image.')
        logger.debug('Data: {}'.format(self.data))
        logger.debug('Image: {}'.format(img))
        logger.debug('Image size: {}'.format(img.size))
        imgsize = self.scale(img.size)
        imgwidth, imgheight = imgsize
        logger.debug('Scaled image size: {}'.format(imgsize))
        logger.debug('Label preset size: {}, {}'.format(self.width, self.height))

        # resize label
        rot_img = False
        if self.height == 0:
            if not self.rotated:
                x = imgwidth
                y = self.width
            else:
                x = imgheight
                y = self.width
        else:
            if not self.rotated:
                x = self.height
                y = self.width
            else:
                x = self.width
                y = self.height

        self.image = Image.new('L', (x, y), 255)

        logger.debug('Label dimensions: {}, {}'.format(x, y))
        logger.debug('Scaled dimensions: {}'.format(imgsize))

        self.label = ImageDraw.Draw(self.image)

        #img = halftone(img.resize(imgsize), 8, 1, 45)
        img = img.resize(imgsize)
        if self.rotated:
            img = img.rotate(angle=90, expand=True)
        self.image.paste(img, (0, 0))

    def qr(self):
        logger.debug('Generating QR-CODE: {}'.format(self.data['qr_text']))

        # TODO: more options on qr-code (plaintext content, box size, etc)
        if 'error_correction' in self.data:
            error_correction = self.data['error_correction']
        else:
            error_correction = 0

        qr = qrcode.QRCode(version=1,
                           error_correction=error_correction,
                           box_size=10,
                           border=1
                          )

        qr.add_data(self.data['qr_text'])
        qr.make()
        qrimage = qr.make_image(fill_color="black", back_color="white")

        qrsize = self.scale(qrimage.size)

        logger.debug('QR Size: {}'.format(qrsize))

        # resize label
        if self.height == 0:
            if not self.rotated:
                x = self.width
                y = qrsize[0]
            else:
                y = qrsize[0]
                x = self.width
        else:
            if not self.rotated:
                x = self.height
                y = self.width
            else:
                x = self.width
                y = self.height

        self.image = Image.new('L', (x, y), 255)
        self.label = ImageDraw.Draw(self.image)
        logger.debug('Label dimensions: {}, {}'.format(x, y))
        logger.debug('Scaled dimensions: {}'.format(qrsize))
        qrimage = qrimage.resize(qrsize)

        pastex = 0
        pastey = 0
        if self.data['qr_align'] == 'center':
            pastex = int((x - qrsize[0]) / 2)
        elif self.data['qr_align'] == 'right':
            pastex = x - qrsize[0]
        self.image.paste(qrimage, (pastex, pastey))
        #self.label.text((0, 0), self.data['qr_text'], 0)

    def text(self):
        left, top, right, bottom = self.label.textbbox(xy=(0, 0), text=self.data['text'], font=self.font, spacing=self.data['font_spacing'])
        x = right - left
        y = bottom - top

        # resize label
        if self.height == 0:
            if not self.rotated:
                self.height = self.width
                self.width = x + self.data['margin_left'] + self.data['margin_right']
            else:
                self.height = y + self.data['margin_top'] + self.data['margin_bottom']
        elif not self.rotated:
            self.height, self.width = LabelsManager()[self.size].dots_printable
        self.image = Image.new('L', (self.width, self.height), 255)
        self.label = ImageDraw.Draw(self.image)

        # horizontal alignment
        if self.data['halign'] == "center":
            x = int(self.width/2) - int(x / 2)
        elif self.data['halign'] == "left":
            x = 0 + self.data['margin_left']
        elif self.data['halign'] == "right":
            x = self.width - (x + self.data['margin_right'])

        # vertical alignment
        if self.data['valign'] == "middle":
            y = int(self.height / 2) - int(y / 2)
        elif self.data['valign'] == "top":
            y = 0 + self.data['margin_top']
        elif self.data['valign'] == "bottom":
            y = self.height - (y + self.data['margin_bottom'])
        self.label.multiline_text(
            (x, y), self.data['text'], 0, font=self.font, align=self.data['halign'], spacing=self.data['font_spacing'])

    def draw(self):
        return self.convert_to_png()

    def prt(self):
        print(LabelsManager()[self.size])
        if LabelsManager()[self.size].form_factor == FormFactor.ENDLESS:
            rot = 0 if self.rotated else 90
        else:
            rot = 'auto'

        if LabelsManager()[self.size].form_factor != FormFactor.ENDLESS:
            LabelsManager()[self.size].feed_margin = config['label']['feed_margin']

        qlr = BrotherQLRaster(config['printer']['model'])
        if qlr.model.cutting:
            logger.debug('Printer is capable of automatic cutting.')
            cutting = True
        else:
            logger.debug('Printer is not capable of automatic cutting.')
            cutting = False
        create_label(qlr, self.image, self.size,
                     threshold=30, cut=cutting, rotate=rot)
        try:
            backend_class = backend_factory(backend)['backend_class']
            be = backend_class(config['printer']['device'])
            pprint(vars(be))
            be.write(qlr.data)
            be.dispose()
            del be
            # TODO better feedback from printer
            return "alert-success", "<b>Success:</b>Label printed"
        except Exception as e:
            logger.warning("unable tp print")
            logger.warning(e)
            return "danger", "unable to print"
