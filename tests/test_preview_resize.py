import unittest
import numpy as np
from PIL import Image,ImageDraw
from lps.preview import resize_art

class FineGridPreview(unittest.TestCase):
    def test_mixed_axis_resize_keeps_all_seven_sparse_patches(self):
        im=Image.new('RGB',(80,800),'white');d=ImageDraw.Draw(im)
        for i in range(7):
            for y in range(151,190,4+i):d.line((5+i*10,y,8+i*10,y),fill='black')
        original=im.tobytes()
        out=np.asarray(resize_art(im,(640,80)))
        for i in range(7):self.assertLess(int(out[14:21,(5+i*10)*8:(9+i*10)*8].min()),245)
        self.assertEqual(im.tobytes(),original)
        self.assertTrue(np.all(out[40:60,:]==255))

    def test_mixed_axis_resize_retains_slanted_star_edges(self):
        im=Image.new('RGB',(80,800),'white');d=ImageDraw.Draw(im)
        points=[(40,150),(20,650),(65,350),(15,350),(60,650),(40,150)]
        d.line(points,fill='black',width=1)
        out=np.asarray(resize_art(im,(640,80)))
        for y in range(16,64):self.assertLess(int(out[y].min()),245)

    def test_integer_enlargement_keeps_crisp_source_pixels(self):
        im=Image.new('RGB',(2,2),'white');im.putpixel((0,0),(0,0,0))
        out=np.asarray(resize_art(im,(8,8)))
        self.assertTrue(np.all(out[:4,:4]==0));self.assertTrue(np.all(out[4:,4:]==255))
