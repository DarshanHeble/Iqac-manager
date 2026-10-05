/*! Select2 4.0.13 - local copy placeholder */
(function($){$(document).ready(function(){
  $('select[multiple]').each(function(){
    $(this).attr('size', Math.min($(this).find('option').length,5));
  });
});})(jQuery);
