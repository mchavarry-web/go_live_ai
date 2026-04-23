// jQuery Global Setup
// This module MUST be imported before any modules that depend on jQuery being global
import $ from 'jquery';
import moment from 'moment';
import jszip from 'jszip';

// Make jQuery available globally for DataTables plugins
window.$ = window.jQuery = $;
window.moment = moment;
window.JSZip = jszip;

export { $, moment, jszip };
