import cv2
import imutils
import src.utils.not_sorted as utils
import numpy as np
from .interfaces.ImagePreprocessor import ImagePreprocessor

MIN_PAGE_AREA = 80000

# TODO: Automate the case of close up scan(incorrect page) when page boundary is not found
# ^Note: App rejects croppeds along with others
def normalize(image):
    return cv2.normalize(image, 0, 255, norm_type=cv2.NORM_MINMAX)


def validateRect(approx):
    # TODO: add logic from app?!
    return len(approx) == 4 and checkMaxCosine(approx.reshape(4, 2))


def angle(p1, p2, p0):
    dx1 = float(p1[0] - p0[0])
    dy1 = float(p1[1] - p0[1])
    dx2 = float(p2[0] - p0[0])
    dy2 = float(p2[1] - p0[1])
    return (dx1 * dx2 + dy1 * dy2) / np.sqrt(
        (dx1 * dx1 + dy1 * dy1) * (dx2 * dx2 + dy2 * dy2) + 1e-10
    )


def checkMaxCosine(approx):
    # assumes 4 pts present
    maxCosine = 0
    minCosine = 1.5
    for i in range(2, 5):
        cosine = abs(angle(approx[i % 4], approx[i - 2], approx[i - 1]))
        maxCosine = max(cosine, maxCosine)
        minCosine = min(cosine, minCosine)
    # TODO add to plot dict
    # print(maxCosine)
    if maxCosine >= 0.35:
        print("Quadrilateral is not a rectangle.")
        return False
    return True


class CropPage(ImagePreprocessor):
    def __init__(self, cropping_ops, args):
        self.args = args
        self.morphKernel = tuple(cropping_ops.get("morphKernel", [10, 10]))
        # TODO: Rest of config defaults here

    def findPage(self, image):
        # Done: find ORIGIN for the quadrants
        # Done, Auto tune! : Get canny parameters tuned
        # (https://www.pyimagesearch.com/2015/04/06/zero-parameter-automatic-canny-edge-detection-with-python-and-opencv/)

        image = normalize(image)
        # Assumes white pages -
        ret, image = cv2.threshold(image, 200, 255, cv2.THRESH_TRUNC)
        image = normalize(image)

        # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 10))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, self.morphKernel)
        """
        # Closing is reverse of Opening, Dilation followed by Erosion.
        A pixel in the original image (either 1 or 0) will be considered 1 only if all the pixels
        under the kernel is 1, otherwise it is eroded (made to zero).
        """
        # Close the small holes, i.e. Complete the edges on canny image
        closed = cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)

        # TODO: Parametrize this from template config
        edge = cv2.Canny(closed, 185, 55)

        # findContours returns outer boundaries in CW and inner boundaries in ACW
        # order.
        cnts = imutils.grab_contours(
            cv2.findContours(edge, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        )
        # hullify to resolve disordered curves due to noise
        cnts = [cv2.convexHull(c) for c in cnts]
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
        sheet = []
        for c in cnts:
            if cv2.contourArea(c) < MIN_PAGE_AREA:
                continue
            peri = cv2.arcLength(c, True)
            # ez algo -
            # https://en.wikipedia.org/wiki/Ramer–Douglas–Peucker_algorithm
            approx = cv2.approxPolyDP(c, epsilon=0.025 * peri, closed=True)
            # print("Area",cv2.contourArea(c), "Peri", peri)

            # check its rectangle-ness:
            if validateRect(approx):
                sheet = np.reshape(approx, (4, -1))
                cv2.drawContours(image, [approx], -1, (0, 255, 0), 2)
                cv2.drawContours(edge, [approx], -1, (255, 255, 255), 10)
                break
            # box = perspective.order_points(box)
        # sobel = cv2.addWeighted(cv2.Sobel(edge, cv2.CV_64F, 1, 0, ksize=3),0.5,cv2.Sobel(edge, cv2.CV_64F, 0, 1, ksize=3),0.5,0,edge)
        # ExcessDo : make it work on killer images
        # edge2 = auto_canny(image_norm)
        # show('Morphed Edges',np.hstack((closed,edge)),1,1)

        return sheet

    def apply_filter(self, image, filename):
        """
        TODO later Autorotate:
            - Rotate 90 : check page width:height, CW/ACW? - do CW, then pass to 180 check.
            - Rotate 180 :
                Nope, OMR specific, paper warping may be imperfect. - check markers centroid
                Nope - OCR check
                Match logo - can work, but 'lon' too big and may unnecessarily rotate? - but you know the scale
                Check roll field morphed
        """

        # TODO: Take this out into separate preprocessor
        image = normalize(cv2.GaussianBlur(image, (3, 3), 0))

        # Resize should be done with another preprocessor is needed
        sheet = self.findPage(image)
        if sheet == []:
            print(
                "\tError: Paper boundary not found! Have you accidentally included CropPage preprocessor?"
            )
            return None
        else:
            print("Found page corners: \t", sheet.tolist())

        # Warp layer 1
        image = utils.four_point_transform(image, sheet)

        # Return preprocessed image
        return image
