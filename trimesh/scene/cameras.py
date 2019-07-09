import copy

import numpy as np

from .. import util
from .. import transformations

from ..geometry import align_vectors


class Camera(object):

    def __init__(
            self,
            name=None,
            resolution=None,
            focal=None,
            fov=None):
        """
        Create a new Camera object that stores camera intrinsic
        and extrinsic parameters.

        TODO: skew is not supported
        TODO: cx and cy that are not half of width and height

        Parameters
        ------------
        name : str or None
          Name for camera to be used as node name
        resolution : (2,) int
          Pixel size in (height, width)
        focal : (2,) float
          Focal length in pixels. Either pass this OR FOV
          but not both.  focal = (K[0][0], K[1][1])
        fov : (2,) float
          Field of view (fovx, fovy) in degrees
        """

        if name is None:
            # if name is not passed, make it something unique
            self.name = 'camera_{}'.format(util.unique_id(6).upper())
        else:
            # otherwise assign it
            self.name = name

        if fov is None and focal is None:
            raise ValueError('either focal length or FOV required!')

        # store whether or not we computed the focal length
        self._focal_computed = False

        # set the passed (2,) float focal length
        self.focal = focal

        # set the passed (2,) float FOV in degrees
        self.fov = fov

        if resolution is None:
            # if unset make resolution 15 pixels per degree
            resolution = (self.fov * 15.0).astype(np.int64)
        self.resolution = resolution

    def copy(self):
        """
        Safely get a copy of the current camera.
        """
        return Camera(
            name=copy.deepcopy(self.name),
            resolution=copy.deepcopy(self.resolution),
            focal=copy.deepcopy(self.focal),
            fov=copy.deepcopy(self.fov))

    @property
    def resolution(self):
        """
        Get the camera resolution in pixels.

        Returns
        ------------
        resolution (2,) float
          Camera resolution in pixels
        """
        return self._resolution

    @resolution.setter
    def resolution(self, values):
        """
        Set the camera resolution in pixels.

        Parameters
        ------------
        resolution (2,) float
          Camera resolution in pixels
        """
        values = np.asanyarray(values, dtype=np.int64)
        if values.shape != (2,):
            raise ValueError('resolution must be (2,) float')
        values.flags.writeable = False
        self._resolution = values
        # unset computed value that depends on the other plus resolution
        if self._focal_computed:
            self._focal = None
        else:
            # fov must be computed
            self._fov = None

    @property
    def focal(self):
        """
        Get the focal length in pixels for the camera.

        Returns
        ------------
        focal : (2,) float
          Focal length in pixels
        """
        if self._focal is None:
            # calculate focal length from FOV
            focal = (
                self._resolution / (2.0 * np.tan(np.radians(self._fov / 2.0))))
            focal.flags.writeable = False
            self._focal = focal

        return self._focal

    @focal.setter
    def focal(self, values):
        """
        Set the focal length in pixels for the camera.

        Returns
        ------------
        focal : (2,) float
          Focal length in pixels.
        """
        if values is None:
            self._focal = None
        else:
            # flag this as not computed (hence fov must be)
            # this is necessary so changes to resolution can reset the
            # computed quantity without changing the explicitly set quantity
            self._focal_computed = False
            values = np.asanyarray(values, dtype=np.float64)
            if values.shape != (2,):
                raise ValueError('focal length must be (2,) float')
            values.flags.writeable = False
            # assign passed values to focal length
            self._focal = values
            # focal overrides FOV
            self._fov = None

    @property
    def K(self):
        """
        Get the intrinsic matrix for the Camera object.

        Returns
        -----------
        K : (3, 3) float
          Intrinsic matrix for camera
        """
        K = np.eye(3, dtype=np.float64)
        K[0, 0] = self.focal[0]
        K[1, 1] = self.focal[1]
        K[:2, 2] = self.resolution / 2.0
        return K

    @K.setter
    def K(self, values):
        if values is None:
            return
        values = np.asanyarray(values, dtype=np.float64)
        if values.shape != (3, 3):
            raise ValueError('matrix must be (3,3)!')

        if not np.allclose(values.flatten()[[1, 3, 6, 7, 8]],
                           [0, 0, 0, 0, 1]):
            raise ValueError(
                'matrix should only have focal length and resolution!')

        # set focal length from matrix
        self.focal = [values[0, 0], values[1, 1]]
        # set resolution from matrix
        self.resolution = values[:2, 2] * 2

    @property
    def fov(self):
        """
        Get the field of view in degrees.

        Returns
        -------------
        fov : (2,) float
          XY field of view in degrees
        """
        if self._fov is None:
            fov = 2.0 * np.degrees(
                np.arctan((self._resolution / 2.0) / self._focal))
            fov.flags.writeable = False
            self._fov = fov
        return self._fov

    @fov.setter
    def fov(self, values):
        """
        Set the field of view in degrees.

        Parameters
        -------------
        values : (2,) float
          Size of FOV to set in degrees
        """
        if values is None:
            self._fov = None
        else:
            # flag this as computed (hence fov must not be)
            # this is necessary so changes to resolution can reset the
            # computed quantity without changing the explicitly set quantity
            self._focal_computed = True
            values = np.asanyarray(values, dtype=np.float64)
            if values.shape != (2,):
                raise ValueError('focal length must be (2,) int')
            values.flags.writeable = False
            # assign passed values to FOV
            self._fov = values
            # fov overrides focal
            self._focal = None

    def to_rays(self, transform):
        """
        Convert a trimesh.scene.Camera object to ray origins
        and direction vectors. Will return one ray per pixel,
        as set in camera.resolution.

        Parameters
        ----------
        transform : (4, 4) float
          Camera transform in the base frame

        Returns
        --------------
        origins : (3,) float
          Ray origin in space
        vectors : (n, 3) float
          Ray direction unit vectors
        """
        return camera_to_rays(self, transform)
    
    def angles(self):
        """
        Get ray spherical coordinates in radians.

        
        Returns
        --------------
        angles : (n, 2) float
          Ray spherical coordinate angles in radians.
        """
        return np.arctan(-_ray_pixel_coords(self))
        


def look_at(points, fov, rotation=None, distance=None, center=None):
    """
    Generate transform for a camera to keep a list
    of points in the camera's field of view.

    Parameters
    -------------
    points : (n, 3) float
      Points in space
    fov : (2,) float
      Field of view, in DEGREES
    rotation : None, or (4, 4) float
      Rotation matrix for initial rotation
    center : None, or (3,) float
      Center of field of view.

    Returns
    --------------
    transform : (4, 4) float
      Transformation matrix with points in view
    """

    if rotation is None:
        rotation = np.eye(4)
    else:
        rotation = np.asanyarray(rotation, dtype=np.float64)
    points = np.asanyarray(points, dtype=np.float64)

    # Transform points to camera frame (just use the rotation part)
    rinv = rotation[:3, :3].T
    points_c = rinv.dot(points.T).T

    if center is None:
        # Find the center of the points' AABB in camera frame
        center_c = points_c.min(axis=0) + 0.5 * points_c.ptp(axis=0)
    else:
        # Transform center to camera frame
        center_c = rinv.dot(center)

    # Re-center the points around the camera-frame origin
    points_c -= center_c

    # Find the minimum distance for the camera from the origin
    # so that all points fit in the view frustrum
    tfov = np.tan(np.radians(fov) / 2.0)

    if distance is None:
        distance = np.max(np.abs(points_c[:, :2]) /
                          tfov + points_c[:, 2][:, np.newaxis])

    # set the pose translation
    center_w = rotation[:3, :3].dot(center_c)
    cam_pose = rotation.copy()
    cam_pose[:3, 3] = center_w + distance * cam_pose[:3, 2]

    return cam_pose


def _ray_pixel_coords(camera):
    bottom_right = np.tan(np.radians(camera.fov / 2.0))
    # move half a pixel width in
    ## pixel_size = (bottom_right - top_left) / camera.resolution
    # pixel_size = bottom_right*2 / camera.resolution
    # bottom_right -= pixel_size / 2
    bottom_right *= 1 - 1. / camera.resolution
    
    top_left = -bottom_right

    xy = util.grid_linspace(
        bounds=[top_left, bottom_right], count=camera.resolution)
    return xy


def camera_to_rays(camera, transform):
    """
    Convert a trimesh.scene.Camera object to ray origins
    and direction vectors. Will return one ray per pixel,
    as set in camera.resolution.

    Parameters
    --------------
    camera : trimesh.scene.Camera
      Camera with transform defined
    transform : (4, 4) float
      Camera transform in the base frame

    Returns
    --------------
    origins : (3,) float
      Ray origins in space
    vectors : (n, 3) float
      Ray direction unit vectors
    """
    xy = _ray_pixel_coords(camera)
    # vectors = util.unitize(np.column_stack((xy, np.ones_like(xy[:, :1]))))
    vectors = np.column_stack((xy, -np.ones_like(xy[:, :1])))

    # flip the camera transform to change sign of Z
    transform = np.dot(
        transform,
        align_vectors([1, 0, 0], [-1, 0, 0]))

    # apply the rotation to the direction vectors
    vectors = transformations.transform_points(
        vectors,
        transform,
        translate=False)

    # camera origin is single point, extract from transform
    origin = transformations.translation_from_matrix(transform)
    return origin, vectors
