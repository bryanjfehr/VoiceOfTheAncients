"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.requestLocationAccuracy = exports.openPhotoPicker = exports.checkLocationAccuracy = exports.canScheduleExactAlarms = void 0;
const getUnsupportedError = (os, version) => new Error(`Only supported by ${os} ${version} and above`);
const canScheduleExactAlarms = async () => {
  throw getUnsupportedError('Android', 12);
};
exports.canScheduleExactAlarms = canScheduleExactAlarms;
const openPhotoPicker = async () => {
  throw getUnsupportedError('iOS', 14);
};
exports.openPhotoPicker = openPhotoPicker;
const requestLocationAccuracy = async () => {
  throw getUnsupportedError('iOS', 14);
};
exports.requestLocationAccuracy = requestLocationAccuracy;
const checkLocationAccuracy = async () => {
  throw getUnsupportedError('iOS', 14);
};
exports.checkLocationAccuracy = checkLocationAccuracy;
//# sourceMappingURL=unsupportedMethods.js.map