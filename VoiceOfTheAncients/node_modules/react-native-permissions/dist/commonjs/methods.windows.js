"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.methods = void 0;
var _reactNative = require("react-native");
var _unsupportedMethods = require("./unsupportedMethods");
var _utils = require("./utils");
const NativeModule = _reactNative.NativeModules.RNPermissions;
const openSettings = async () => {
  await NativeModule.OpenSettings();
};
const check = permission => {
  return NativeModule.Check(permission);
};
const request = permission => {
  return NativeModule.Request(permission);
};
const checkNotifications = async () => {
  const status = await NativeModule.CheckNotifications();
  return {
    status,
    settings: {}
  };
};
const checkMultiple = async permissions => {
  const output = {};
  for (const permission of (0, _utils.uniq)(permissions)) {
    output[permission] = await check(permission);
  }
  return output;
};
const requestMultiple = async permissions => {
  const output = {};
  for (const permission of (0, _utils.uniq)(permissions)) {
    output[permission] = await request(permission);
  }
  return output;
};
const methods = exports.methods = {
  canScheduleExactAlarms: _unsupportedMethods.canScheduleExactAlarms,
  check,
  checkLocationAccuracy: _unsupportedMethods.checkLocationAccuracy,
  checkMultiple,
  checkNotifications,
  openPhotoPicker: _unsupportedMethods.openPhotoPicker,
  openSettings,
  request,
  requestLocationAccuracy: _unsupportedMethods.requestLocationAccuracy,
  requestMultiple,
  requestNotifications: checkNotifications
};
//# sourceMappingURL=methods.windows.js.map