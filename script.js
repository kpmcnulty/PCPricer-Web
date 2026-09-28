const tabcolor = '#001c6a';
var CPUprice = 0;
var CPUage = 0;

var dateTime = new Date();
const year = dateTime.getFullYear();
const expressions = false;
const highlightColor = 'orange';
$(window).resize(function() { onResize() });

$(document).ready(async function() {
  await $.getJSON("data.json", function(data) {
    RAMs = data.ram;
    CPU.comps = data.cpu;
    GPU.comps = data.gpu;
    PSUs = data.psu;
    params = data.params;
    dp = data.driveparams;
    updated = data.updated;
  });

  if (updated) {
    const date = new Date(updated + 'T00:00:00');
    $('#data-updated').text('    |    Prices updated ' +date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }));
  }

  PSUs.ratings = ['Unrated/Bronze', 'Silver/Gold', 'Platinum/Titanium'];

  cpuparams = {
    a: params.cpu_a, b: params.cpu_b, c: params.cpu_c, d: params.cpu_d,
    label: ' ', color: Desmos.Colors.BLUE
  };
  cputimeparams = { w: params.cpu_decay, label: ' ', color: Desmos.Colors.BLACK };

  gpuparams = {
    a: params.gpu_a, b: params.gpu_b, c: params.gpu_c, d: params.gpu_d,
    label: ' ', color: Desmos.Colors.PURPLE
  };
  gputimeparams = { w: params.gpu_decay, label: ' ', color: Desmos.Colors.BLACK };

  driveparams = [{
    a: dp.hdd_a, b: dp.hdd_b, c: dp.hdd_c, d: dp.hdd_d, label: ' HDD',
    color: Desmos.Colors.ORANGE, func: ypoly, strFunc: ypolyString
  },
  {
    a: dp.ssd_a, b: dp.ssd_b, c: dp.ssd_c, d: dp.ssd_d,
    color: Desmos.Colors.PURPLE, label: ' SSD', func: ypoly, strFunc: ypolyString
  }];
  drivetimeparams = [{ w: dp.hdd_decay, label: ' HDD', color: Desmos.Colors.ORANGE },
  { w: dp.ssd_decay, label: ' SSD', color: Desmos.Colors.PURPLE }];

  ramparams = [{ a: RAMs.ddr4_a, b: RAMs.ddr4_b, label: 'DDR4', color: Desmos.Colors.RED },
  { a: RAMs.ddr5_a, b: RAMs.ddr5_b, label: 'DDR5', color: Desmos.Colors.BLUE }];
  ramtimeparams = { w: RAMs.decay, label: ' ', color: Desmos.Colors.BLACK };

  psuparams = [{ a: PSUs.low_a, b: PSUs.low_b, c: PSUs.low_c, label: 'Unrated/Bronze', color: '#b87333', },
  { a: PSUs.mid_a, b: PSUs.mid_b, c: PSUs.mid_c, label: 'Silver/Gold', color: '#d4af37' },
  { a: PSUs.high_a, b: PSUs.high_b, c: PSUs.high_c, label: 'Platinum/Titanium', color: '#b4b2a7' }];
  psutimeparams = { w: PSUs.decay, factor: PSUs.used_factor, label: ' ', color: Desmos.Colors.BLACK };


  fillLists(GPU);
  fillLists(CPU);

  onResize();

  $('select').on('input', function() {
    if ($(this).val() == -1) {
      $(this).css('color', 'blue');
    } else {
      $(this).css('color', 'black');
    }
  });//.val(-1);

  $('.checkbox').prop('checked', false);
  $('.checkbox').prop('disabled', true);
  $('.slider').prop('disabled', false);

  $('#share-button').click(function() { copyToClipboard("https://pcpricer.net" + getUrlParams()) });

  RAMgraph = newGraph('RAMgraph', 40, 150, ramparams, linearString);
  RAMtimegraph = newGraph('RAMtimegraph', 25, 1, ramtimeparams, decayString);
  Drivegraph = newGraph('Drivegraph', 2000, 50, driveparams);
  CPUgraph = newGraph('CPUgraph', 25000, 1200, cpuparams, polyString);
  CPUtimegraph = newGraph('CPUtimegraph', 25, 1, cputimeparams, decayString);
  GPUgraph = newGraph('GPUgraph', 25000, 1200, gpuparams, polyString);
  GPUtimegraph = newGraph('GPUtimegraph', 25, 1, gputimeparams, decayString);
  PSUgraph = newGraph('PSUgraph', 1500, 300, psuparams, lnString);
  Drivetimegraph = newGraph('Drivetimegraph', 25, 1, drivetimeparams, decayString);
  PSUtimegraph = newGraph('PSUtimegraph', 25, 1, psutimeparams, decayString);

  urlParams = new URLSearchParams(window.location.search);

  // Old share links can include parts the site no longer prices; drop them from the address bar.
  if (urlParams.has('mobo') || urlParams.has('case')) {
    urlParams.delete('mobo');
    urlParams.delete('case');
    const query = urlParams.toString();
    history.replaceState(null, '', location.pathname + (query ? '?' + query : '') + location.hash);
  }

  for (const c of compObjects) {
    if (urlParams.has(c.name)) {
      var comps = urlParams.getAll(c.name);
      for (const comp of comps) {
        var p = comp.split('-');
        if (p.length == 1) {
          add(c, p[0]);
        } else {
          add(c, p);
        }
      }
    }
  }

  setupSlider('#ramsizewrapper', RAM.update, 1, 256, function(val) { return Math.pow(2, val) }, Math.log2, RAM, false);
  setupSlider('#drivesizewrapper', drive.update, 50, 16000, getDriveSize, getDriveSizeInverse, drive, false);
  setupSlider('#psuwattagewrapper', PSU.update, 250, 1500, function(val) { return 50 * val + 250 }, function(val) { return (val - 250) / 50 }, PSU, false);
  setupSlider('#driveagewrapper', drive.update, 0, 25, null, null, drive, true);

  $('.slider').trigger('input');

  hideDetails("CPUdata");
  hideDetails("GPUdata");

  RAM.update();
  drive.update();
  PSU.update();

  total();

  setupGraphSwaps(CPU);
  setupGraphSwaps(GPU);
  setupGraphSwaps(RAM);
  setupGraphSwaps(drive);
  setupGraphSwaps(PSU);

  $('#loading-page').hide();
  openTab(0);
  //$('#About').show();

});



CPU = {
  updateGraphs: function(id) {
    var comp = getComp(CPU, id);
    var p = showPoint(CPUgraph, comp.bench, poly, cpuparams);
    var v = showPoint(CPUtimegraph, comp.age / 365, decay, cputimeparams);

    updateProduct("#CPUproduct", p, v);
    $('.checkbox').prop('disabled', false);

    RAM.update();
  },

  getNamePrice: function(id) {
    var comp = getComp(CPU, id);
    CPUage = comp.age;
    CPUprice = Math.round(poly(comp.bench, cpuparams) * decay(comp.age / 365, cputimeparams));
    RAM.update();

    return { price: CPUprice, name: comp.name }
  },

  el: '#CPU',
  name: 'cpu',

  right: 0
};

GPU = {
  el: '#GPU',
  name: 'gpu',

  getNamePrice: function(id) {
    var comp = getComp(GPU, id);

    return { price: poly(comp.bench, gpuparams) * decay(comp.age / 365, gputimeparams), name: comp.name }
  },

  updateGraphs: function(id) {
    var comp = getComp(GPU, id);
    var p = showPoint(GPUgraph, comp.bench, poly, gpuparams);
    var v = showPoint(GPUtimegraph, comp.age / 365, decay, gputimeparams);


    updateProduct("#GPUproduct", p, v);
  },

  right: 0
};

const getComp = function(obj, id) {
  return obj.comps.find(x => x.idp == id);
}

drive = {   //[type, size]
  update: function() {
    var drivetype = $("#driveTypeSelect").val();
    var drivesize = $('#drivesizebox').val();

    upDet(drive, [drivetype, drivesize, getAge('#driveagewrapper')]);
  },


  updateGraphs: function(p) {
    var d = driveparams[p[0]];
    var c = showPoint(Drivegraph, p[1], d.func, d);
    var w = showPoint(Drivetimegraph, p[2], decay, drivetimeparams[p[0]]);
    updateProduct('#Driveproduct', c, w);
  },

  getNamePrice: function(p) {
    var d = driveparams[p[0]];
    return { name: prettySize(p[1]) + d.label + prettyAge(p[2]), price: d.func(p[1], d) * decay(p[2], drivetimeparams[p[0]]) }
  },

  el: '#Drive',
  name: 'drive',
  quantity: 0,
  tab: 2,
  obj: 'drive',
  right: 0
};

RAM_TYPES = ['ddr4', 'ddr5'];

// Share links before DDR5 was added used [age, size]; anything that isn't a type is DDR4.
function ramType(t) {
  return Math.max(RAM_TYPES.indexOf(t), 0);
}

RAM = {   //[type, size]
  update: function() {
    var RAMsize = $('#ramsizebox').val();

    $('#ramsizebox').val(RAMsize);

    upDet(RAM, [$('#ramTypeSelect').val(), RAMsize]);
  },

  updateGraphs: function(p) {
    var c = showPoint(RAMgraph, p[1], linear, ramparams[ramType(p[0])]);
    var w = showPoint(RAMtimegraph, 0, decay, ramtimeparams);

    updateProduct('#RAMproduct', c, w)
  },

  getNamePrice: function(p) {
    var r = ramparams[ramType(p[0])];
    return { name: p[1] + 'GB ' + r.label + ' RAM', price: linear(p[1], r) }
  },

  el: '#RAM',
  name: 'ram',
  quantity: 0,
  tab: 3,
  obj: 'RAM',
  right: 0
}

function getAge(wrapper) {
  var checkedVal = (CPUage / 365).toFixed(0);
  return getValWithCheckbox(wrapper, checkedVal)
}

function getValWithCheckbox(wrapper, checkedVal, inverseFunc) {
  wrapper = $(wrapper);
  const box = wrapper.find('.slide-value');
  const slider = wrapper.find('.slider');
  const checkbox = wrapper.find('.checkbox');

  if (checkbox.prop('checked') == true) {
    slider.prop('disabled', true);
    var val = checkedVal;
    var inverseVal = val;
    box.val(val);
    if (inverseFunc) {
      inverseVal = inverseFunc(val);
    }
    slider.val(inverseVal);

  } else {
    slider.prop('disabled', false);
    var val = box.val();
  }

  return val;
}


PSU = {
  update: function() {
    var i = $('#psuwattagebox').val();
    var j = $('#ratingselect').val();
    if (j != null) {
      upDet(PSU, [i, j]);
    } else {
      hideDetails('PSUdata');
    }
  },

  updateGraphs: function(p) {
    var c = showPoint(PSUgraph, p[0], ln, psuparams[p[1]]);
    var w = showPoint(PSUtimegraph, 0, decay, psutimeparams);

    updateProduct('#PSUproduct', c, w);
  },

  getNamePrice: function(p) {
    // Share links before Sep 2026 had an age as p[2]; used PSUs sell for about the same at any age.
    return { name: [" Bronze ", " Gold ", " Plt/Ttm "][p[1]] + p[0] + "W PSU", price: ln(p[0], psuparams[p[1]]) * decay(0, psutimeparams) }
  },

  right: 0,
  el: '#PSU',
  name: 'psu',
};


compObjects = [CPU, GPU, drive, RAM, PSU];


//setup functions: 

// The search lists hold thousands of parts, so only matches are rendered (see filter).
const MAX_SEARCH_RESULTS = 100;

function fillLists(obj) {
  for (const comp of obj.comps) {
    comp.searchKey = clean(comp.name);
  }
}


function updateProduct(id, benchprice, value) {
  spans = $('span .value', id);
  price = Math.round(benchprice * value)
  $(spans[0]).text(Math.round(benchprice));
  $(spans[1]).text(value.toFixed(2));
  $(spans[2]).text('$' + price);

  return price
}

function addOptions(parentId, options, extra) {
  parent = document.getElementById(parentId);

  for (var i = 0; i < options.length; i++) {
    option = document.createElement("option");
    parent.appendChild(option);
    option.setAttribute("value", i);

    option.innerHTML = options[i] + extra;
  }
}

function setupSlider(parent, u, min, max, stb, bts, graphs, leftright) {
  var slider = $(parent).find('.slider');
  var box = $(parent).find('.slide-value');

  box.prop('max', max).prop('min', min);

  if (!stb) {
    var stb = function(x) { return x };
    var bts = stb;
  }

  slider.prop('max', bts(max)).prop('min', bts(min));

  var updateAndSlide = u;
  if (graphs && leftright != null) {
    updateAndSlide = function() {
      slide(graphs, leftright);
      u();
    }
  }

  const up = function() {
    if (clean(box.val()) == '') {
      slideIn();
    } else {
      box.val(clamp(box.val(), min, max));
    }
    updateAndSlide();
  }

  const slideIn = function() { box.val(stb(slider.val())) }

  slider.on('input', slideIn).on('mouseup', updateAndSlide).on('touchend', updateAndSlide);
  box.on('focus', function() { box.val('') }).on('blur', up).on('input', function() { slider.val(bts(clamp(box.val(), min, max))) }).on('keyup', function(event) { if (event.keyCode == 13) { up() } });
}

// Desmos calculators are expensive, so a graph is only created the first time its tab is
// shown (see showGraphsIn). Until then, showPoint just records where the view should be.
const graphs = {};

function newGraph(id, domain, range, params, strFunc) {
  const graph = {
    id: id, params: params, strFunc: strFunc, calc: null, point: null,
    domain: domain, targetDomain: domain, range: range, targetRange: range
  };
  graphs[id] = graph;
  return graph;
}

function showGraphsIn(pageName) {
  $('#' + pageName + ' .graph').each(function() {
    const graph = graphs[this.id];
    if (graph && !graph.calc) {
      createCalculator(graph);
    }
  });
}

function createCalculator(graph) {
  const graphoptions = {
    expressions: expressions,
    settingsMenu: false,
    zoomButtons: false,
    lockViewport: true,
    pointsOfInterest: false
  };

  var letters = ['h', 'g', 'z', 'a', 'b', 'c']

  var chart = Desmos.GraphingCalculator(document.getElementById(graph.id), graphoptions);
  graph.calc = chart;

  // Start at the latest target view rather than animating to it.
  graph.domain = graph.targetDomain;
  graph.range = graph.targetRange;
  chart.setMathBounds({ left: 0, right: graph.domain, bottom: 0, top: graph.range });

  var params = graph.params;
  var strFunc = graph.strFunc;
  var i = 0;

  if (!params.length) {
    params = [params];
  }
  if (!params[0].length) {
    params = [params];
  }

  for (const inner of params) {
    for (const p of inner) {
      if (!strFunc) {
        var str = p.strFunc;
      } else {
        var str = strFunc;
      }

      chart.setExpression({
        id: p.label,
        latex: str(p, letters[i]) + ' \\left\\{x>0\\right\\}',
        color: p.color
      });
      chart.setExpression({
        id: p.label + 'label',
        latex: '(p, ' + letters[i] + '(p))',
        hidden: true,
        showLabel: true,
        label: p.label,
        color: p.color
      });
      i += 1;
    }
  }

  chart.setExpression({
    id: 'label',
    latex: 'p = ' + .3 * graph.domain
  })

  if (graph.point) {
    chart.setExpression(graph.point);
  }
}

function setupGraphSwaps(graphs) {
  var swaps = $(graphs.el).find('.graph-swap');
  var products = $(graphs.el).find('.product span')
  console.log(products)
  const slideLeft = function() { slide(graphs, false) }
  const slideRight = function() { slide(graphs, true) }
  $(swaps[0]).hide().click(slideLeft);
  $(swaps[1]).click(slideRight);
  $(products[0]).click(slideLeft);
  $(products[1]).click(slideRight);
}

//update functions

function upDet(c, p) {
  if (c.updateGraphs) {
    c.updateGraphs(p);
  }

  var np = c.getNamePrice(p);

  var parent = $(c.el).find('.details')

  parent.show();
  parent.find('.name span').text(np.name);
  parent.find('.price span').text('$' + Math.round(np.price));
  parent.find('.addButton').off('click').click(function() { add(c, p) });
}

function updateDetails(comp) {
  var parent = $(comp.el).find('.details')

  parent.show();
  parent.find('.name span').text(comp.name);
  parent.find('.price span').text('$' + comp.price);
  parent.find('.addButton').off('click').click(function() { add(comp, comp.p) });
}


function hideDetails(parentId) {
  drivedetails = $('#' + parentId);

  drivedetails.show();
  drivedetails.find('.name span').text('--');
  drivedetails.find('.price span').text('--');
}

function add(c, p) {
  var se = $(c.el.replace('#', '#build'));

  if (c.quantity != undefined) {
    if (c.quantity > 0) {
      const n = $('<div url="0" class="component"><button class="buildButton" onclick="openTab(' + c.tab + ')"><div class="name">None Selected</div><div value="0" class="price"></div></button><button class="removeButton" onClick="remove(this.parentElement, ' + c.obj + ')"><image src="images/x.png"></button></div>');
      se.append(n);
      se = n;
    } else {
      se = se.find('.component');
    }
    c.quantity++;
  } else {

  }

  var np = c.getNamePrice(p);


  var price = Math.round(np.price);
  se.find('.price').text('$' + price).attr('value', price);
  se.attr('url', c.name + '=' + join(p, '-')).find('.name').text(np.name.split('@')[0]);
  se.find('.buildButton').click(function() { upDet(c, p) }).css('color', '#333');
  se.find('.removeButton').show();

  openSystem();

  total();
}

function join(arr, jc) {
  if (typeof (arr) != 'object') {
    return arr
  }
  var j = arr[0];
  for (i = 1; i < arr.length; i++) {
    j += jc + arr[i];
  }
  return j
}

function remove(parent, c) {
  parent = $(parent);
  parent.find(".name").text('None Selected');
  parent.find('.price').text('').attr('value', 0);
  parent.find('button').off('click').css('color', '#999');
  parent.attr("url", 0).find('.removeButton').hide();
  if (c) {
    if (c.quantity) {
      c.quantity--;
      if (c.quantity > 0) {
        parent.remove();
      }
    }
  }

  total();
}


function total() {
  var priceElements = document.getElementsByClassName("price");
  var totalPrice = 0;
  for (var i = 0; i < priceElements.length; i++) {
    totalPrice += Number(priceElements[i].getAttribute("value"));
  }
  var totalElement = document.getElementById("buildTotal");
  totalElement.innerHTML = "$" + totalPrice;
}

function getUrlParams() {
  var elements = document.getElementsByClassName("component");

  var begun = false;
  var url = '';

  for (var i = 0; i < elements.length; i++) {
    var param = elements[i].getAttribute("url");

    if (param != 0) {

      if (begun) {
        url += '&';
      } else {
        url += '?';
      }

      begun = true;

      url += param
    }
  }
  return url;
}

//graph stuff

function showPoint(graph, x, func, params) {
  var y = func(x, params);

  graph.point = {
    id: 'point',
    latex: '(' + x + ',' + y + ')',
    showLabel: true,
    color: params.color
  };

  if (graph.calc) {
    graph.calc.setExpression(graph.point);
  }

  pan(graph, 2 * x, 2 * y);

  return Number(y);
}

function pan(graph, x, y) {
  graph.targetRange = clamp(y, 1, 9999999);
  graph.targetDomain = clamp(x, 1, 9999999);

  if (graph.calc) {
    panGraph(graph);
    graph.calc.updateSettings({ lockViewport: true });
  }
}

async function panGraph(graph) {
  var chart = graph.calc;
  var rangedif = graph.targetRange - graph.range;
  var domaindif = graph.targetDomain - graph.domain;

  var notdone = false;

  if (Math.abs(rangedif) > Math.abs(graph.targetRange / 1000)) {
    graph.range += rangedif / 8;
    notdone = true;
  }

  if (Math.abs(domaindif) > Math.abs(graph.targetDomain / 1000)) {
    graph.domain += domaindif / 8;
    notdone = true;
  }

  chart.setExpression({
    id: 'label',
    latex: 'p = ' + .3 * graph.domain
  });

  chart.setMathBounds({
    left: 0,
    right: graph.domain,
    bottom: 0,
    top: graph.range
  });

  if (notdone) {
    setTimeout(function() { panGraph(graph) }, 35);
  } else {
    chart.updateSettings({ lockViewport: true });
  }
}


function slide(graphs, left) {
  twoGraphs = $(graphs.el).find('.two-graphs');
  if (left) {
    twoGraphs.css('left', 'calc(-100% - 10px)');
    twoGraphs.css('right',);
  } else {
    twoGraphs.css('right', '');
    twoGraphs.css('left', '0');
  }

  if (left) {
    var i = 1;
  } else {
    var i = 0;
  }

  var swaps = $(graphs.el).find('.graph-swap');
  var spans = $(graphs.el).find('.product span');

  $(swaps[i]).hide();
  $(swaps[1 - i]).show();

  $(spans[i]).css('color', highlightColor);
  $(spans[1 - i]).css('color', 'black');

  //swapGraphExtras(graphs.el, left);
}

/*async function slideGraphs(graphs) {
  var speed = .3;

  var rightdif = graphs.targetRight - graphs.right;

  var res = 1;

  var notdone = false;
	
  var add = rightdif*speed;
  if(Math.abs(rightdif) > res){
    graphs.right += add;
    notdone = true;
  }

  $(graphs.el).find('.two-graphs').css('right', graphs.right + 'px');

  if(notdone) {
    setTimeout(function () {slideGraphs(graphs)}, 45);
  }
}

function swapGraphExtras(el, left){
  if(left){
    var i = 1;
  } else {
    var i = 0;
  }

  var swaps = $(el).find('.graph-swap');
  var spans = $(el).find('.product span');

  $(swaps[i]).hide();
  $(swaps[1-i]).show();

  $(spans[i]).css('color', highlightColor);
  $(spans[1-i]).css('color', 'black'); 	
}*/

function clamp(x, a, b) {
  if (x < a) { return a }
  else if (x > b) { return b }
  else { return x }
}

function openTab(i) {
  $($('.tablink')[i]).click();
}

function resetShareButton() {
  $('#share-button').text('Copy Share Link');
}

const copyToClipboard = str => {
  $('#share-button').text('Copied!');
  setTimeout(resetShareButton, 1000);

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(str);
    return;
  }

  // Fallback for browsers without the async clipboard API.
  const el = document.createElement('textarea');
  el.value = str;
  el.setAttribute('readonly', '');
  el.style.position = 'absolute';
  el.style.left = '-9999px';
  document.body.appendChild(el);
  const selected =
    document.getSelection().rangeCount > 0 ? document.getSelection().getRangeAt(0) : false;
  el.select();
  document.execCommand('copy');
  document.body.removeChild(el);
  if (selected) {
    document.getSelection().removeAllRanges();
    document.getSelection().addRange(selected);
  }
};

function openPage(pageName, elmnt, color) {
  $('.main-content').show();
  var i, tabcontent, tablinks;
  var tabcontent = document.getElementsByClassName("tabcontent");
  for (i = 0; i < tabcontent.length; i++) {
    tabcontent[i].style.display = "none";
  }
  var tablinks = document.getElementsByClassName("tablink");
  for (i = 0; i < tablinks.length; i++) {
    tablinks[i].style.backgroundColor = "";
  }
  document.getElementById(pageName).style.display = "block";
  showGraphsIn(pageName);
  if (elmnt) {
    elmnt.style.backgroundColor = color;
  }
}

function filter(inputId, listId) {
  const obj = listId == 'CPUlist' ? CPU : GPU;
  const query = clean(document.getElementById(inputId).value);
  const list = $('#' + listId).empty();

  if (query == '') {
    return;
  }

  var shown = 0;
  for (const comp of obj.comps) {
    if (comp.searchKey.indexOf(query) > -1) {
      const button = $('<button>').text(comp.name).click(function() { list.hide(); upDet(obj, comp.idp) });
      list.append($('<li>').append(button));
      if (++shown >= MAX_SEARCH_RESULTS) {
        break;
      }
    }
  }
}

function clean(str) {
  str = str.toUpperCase();
  str = str.replace(/ /g, '');
  str = str.replace(/-/g, '');
  return (str);
}

function poly(x, p) {
  return p.a * x * x * x * x + p.b * x * x * x + p.c * x * x + p.d * x;
}

function polyString(p, l) {
  if (!l) {
    var l = 'h';
  }
  return l + '(x)=' + p.a.toFixed(20) + 'x^4+' + p.b.toFixed(20) + 'x^3+' + p.c.toFixed(20) + 'x^2+' + p.d.toFixed(20) + 'x';
}

function ln(x, p) {
  return p.a * Math.log(p.b * x + 1) + p.c * x;
}

function lnString(p, l) {
  if (!l) {
    var l = 'h';
  }
  return l + '(x) =' + p.a.toFixed(20) + '\\ln(' + p.b.toFixed(20) + 'x + 1) + x*' + p.c.toFixed(20);
}

function ypoly(x, p) {
  return p.a * x * x * x + p.b * x * x + p.c * x + p.d;
}

function ypolyString(p, l) {
  if (!l) {
    var l = 'h';
  }
  return l + '(x) =' + p.a.toFixed(20) + 'x^3+' + p.b.toFixed(20) + 'x^2+' + p.c.toFixed(20) + 'x+' + p.d.toFixed(20)
}

function linear(x, p) {
  return p.a * x + p.b;
}

function linearString(p, l) {
  if (!l) {
    var l = 'h';
  }
  return l + '(x) =' + p.a.toFixed(20) + 'x + ' + p.b.toFixed(20);
}

// Share of the new price a used part is worth: p.factor (default 1) times the age decay.
// p.w is null for parts whose value doesn't depend on age (RAM, PSUs).
function decayString(p, l) {
  if (!l) {
    var l = 'h';
  }
  var factor = p.factor || 1;
  if (!p.w) {
    return l + '(x)=' + factor;
  }
  return l + '(x)=' + factor + 'e^{(x*365)^2/' + p.w.toString() + '}';
}

function decay(x, p) {
  var factor = p.factor || 1;
  if (!p.w) {
    return factor.toFixed(2);
  }
  return (factor * Math.exp(Math.pow((x * 365), 2) / p.w)).toFixed(2);
}

function showList(list) {
  $('ul', list).show();
}

function hideList(list) {
  setTimeout(function() {
    if (!$(document.activeElement).is('li button')) {
      $('ul', list).hide();
    }
  }, 10);
}

function openPop(pop) {
  $('span', pop).css('visibility', 'visible');
}
function closePop(pop) {
  $('span', pop).css('visibility', 'hidden');
}

function clearInput(e) {
  $(e).val('');
}

function onResize() {
  var width = $('.main').width() / 2;
  var height = $('.main').height() / 1.3;

  if (width > height) {
    var max = height;
  } else {
    var max = width;
  }

  if (max > 500) {
    $('body').css('--graph-size', '450px');
    graphsize = 450;
  } else {
    $('body').css('--graph-size', '350px');
    graphsize = 350;
  }
}

function getDriveSize(val) {
  if (val <= 45) {
    return 10 * val + 50;
  } else if (val < 56) {
    return (val - 35) * 50;
  } else if (val < 66) {
    return (val - 45) * 100;
  } else {
    return (val - 64) * 1000;
  }
}

function getDriveSizeInverse(size) {
  if (size < 500) {
    return (size - 50) / 10;
  } else if (size < 1000) {
    return (size / 50) + 35;
  } else if (size < 2000) {
    return (size / 100) + 45;
  } else {
    return (size / 1000) + 64;
  }
}

function prettySize(size) {
  if (size < 1000) {
    return size + 'GB';
  } else {
    return size / 1000 + 'TB';
  }
}

function prettyAge(age) {
  return ' (' + (year - age).toString() + ')'
}

function ebayLink(el, hasAge) {
  var searchterm = $(el).parent().find('.name').text();

  if (hasAge) {
    searchterm = searchterm.slice(0, searchterm.length - 6);
  }


  var splitTerm = searchterm.replace(/ /g, '%2B');
  var ebaylink = "https://rover.ebay.com/rover/1/711-53200-19255-0/1?ff3=4&toolid=10041&campid=5338736140&customid=&lgeo=1&mpre=http%3A%2F%2Fwww.ebay.com%2Fsch%2Fi.html%3F_nkw%3D" + splitTerm + "%26_ddo%3D1%26_ipg%3D100%26_pgn%3D1"

  window.open(ebaylink, '_blank');
}

function toggleSystem(button) {

  var sidebar = document.getElementById('sidebar');
  var stylesheet = document.getElementById('toggle-system-stylesheet');
  var button = document.getElementById('toggle-system');

  if (sidebar.style.right == '0px') {
    /*close*/
    stylesheet.href = "toggle-system-collapsed.css"
    sidebar.style = "right: -380px; opacity: 0";
    button.style = "width: 120px";
  } else {
    /*expand*/
    stylesheet.href = "toggle-system-expanded.css";
    button.style = "width: 100%";
    sidebar.style = "right: 0px; opacity: 1";

  }
}

function openSystem() {
  var sidebar = document.getElementById('sidebar');
  var stylesheet = document.getElementById('toggle-system-stylesheet');
  var button = document.getElementById('toggle-system');

  stylesheet.href = "toggle-system-expanded.css";
  button.style = "width: 100%";
  sidebar.style = "right: 0px; opacity: 1";
}

function closeSystem() {
  var sidebar = document.getElementById('sidebar');
  var stylesheet = document.getElementById('toggle-system-stylesheet');
  var button = document.getElementById('toggle-system');

  stylesheet.href = "toggle-system-collapsed.css"
  sidebar.style = "right: -380px; opacity: 0";
  button.style = "width: 120px";
}
