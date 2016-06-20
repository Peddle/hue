## Licensed to Cloudera, Inc. under one
## or more contributor license agreements.  See the NOTICE file
## distributed with this work for additional information
## regarding copyright ownership.  Cloudera, Inc. licenses this file
## to you under the Apache License, Version 2.0 (the
## "License"); you may not use this file except in compliance
## with the License.  You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

<%!
  from desktop.views import commonheader, commonfooter, commonshare, commonimportexport
  from django.utils.translation import ugettext as _
%>
<%namespace name="actionbar" file="actionbar.mako" />

${ commonheader(_("Solr Indexes"), "search", user, "60px") | n,unicode }


<div class="container-fluid">
  <div class="card card-small">
  <h1 class="card-heading simple">${ _('Solr Indexer') }</h1>
  </div>
</div>


<!-- ko template: 'create-index-wizard' --><!-- /ko -->

<script type="text/html" id="create-index-wizard">
  <div class="snippet-settings" data-bind="visible: createWizard.show" style="
  text-align: center;">

    <div class="form-inline">
      <label for="collectionName">${ _('Name') }</label>
      <input class="form-control" id = "collectionName" data-bind="value: createWizard.fileFormat().name">

      <label for="path">${ _('Path') }</label>
      <input class="form-control" id = "path" data-bind="value: createWizard.fileFormat().path">

      <a href="javascript:void(0)" class="btn" data-bind="click: createWizard.guessFormat">Guess Format</a>
    </div>


    <div data-bind="visible: createWizard.fileFormat().show">
      <div data-bind="with: createWizard.fileFormat().format">
          <h3>File Type: <span data-bind="text: type"></span></h3>
          <h4>Has Header:</h4>
          <input type="checkbox" data-bind="checked: hasHeader">

          <h4>Quote Character:</h4>
          <input data-bind="value: quoteChar">
          <h4>Record Separator:</h4>
          <input data-bind="value: recordSeparator">
          <h4>Field Separator:</h4>
          <input data-bind="value: fieldSeparator">
        </div>

        <h3> Fields</h3>
        <ul data-bind="foreach: createWizard.fileFormat().columns">
          <li>
            <input data-bind="value: name"></input> - <select data-bind="options: $parent.createWizard.fileFormat().types, value: type"></select>
          </li>
        </ul>

        <h3> Preview</h3>
        <table style="margin:auto;text-align:left">
          <thead>
            <tr data-bind="foreach: createWizard.fileFormat().columns">
              <th data-bind="text: name" style="padding-right:60px">
              </th>
            </tr>
          </thead>
          <tbody data-bind="foreach: createWizard.sample">
            <tr data-bind="foreach: $data">
              <td data-bind="text: $data">
              </td>
            </tr>
          </tbody>
        </table>

        <br><hr><br>

        <a href="javascript:void(0)" class="btn" data-bind="visible: !createWizard.indexingStarted(), click: createWizard.indexFile">Index File!</a>

        <a href="javascript:void(0)" class="btn btn-success" data-bind="visible: createWizard.jobId, attr: {           href: '/oozie/list_oozie_workflow/' + createWizard.jobId() }" target="_blank" title="${ _('Open') }">
          View Indexing Status
        </a>

      </div>

    <br/>
  </div>
</script>

<div class="hueOverlay" data-bind="visible: isLoading">
  <!--[if lte IE 9]>
    <img src="${ static('desktop/art/spinner-big.gif') }" />
  <![endif]-->
  <!--[if !IE]> -->
    <i class="fa fa-spinner fa-spin"></i>
  <!-- <![endif]-->
</div>


<script src="${ static('desktop/ext/js/datatables-paging-0.1.js') }" type="text/javascript" charset="utf-8"></script>
<script src="${ static('desktop/ext/js/knockout.min.js') }" type="text/javascript" charset="utf-8"></script>
<script src="${ static('desktop/ext/js/knockout-mapping.min.js') }" type="text/javascript" charset="utf-8"></script>


<script type="text/javascript" charset="utf-8">
  var File_Format = function (vm) {
    var self = this;

    self.types = ko.observableArray([
      "string",
      "int",
      "long"
      ]);

    self.name = ko.observable('test');
    self.sample = ko.observableArray();
    self.show = ko.observable(false);

    self.path = ko.observable('/tmp/test.csv');
    self.format = ko.observable();
    self.columns = ko.observableArray();
  };

  var CreateWizard = function (vm) {
    var self = this;
    var guessFieldTypesXhr;

    self.show = ko.observable(true);
    self.showCreate = ko.observable(false);
    
    self.fileFormat = ko.observable(new File_Format(vm));

    self.sample = ko.observableArray();

    self.jobId = ko.observable(null);

    self.indexingStarted = ko.observable(false);

    self.fileFormat().format.subscribe(function(){
      console.log("call back!");
      self.fileFormat().format().quoteChar.subscribe(self.guessFieldTypes);
      self.fileFormat().format().recordSeparator.subscribe(self.guessFieldTypes);
      self.fileFormat().format().type.subscribe(self.guessFieldTypes);
      self.fileFormat().format().hasHeader.subscribe(self.guessFieldTypes);
      self.fileFormat().format().fieldSeparator.subscribe(self.guessFieldTypes);

      self.guessFieldTypes();
    });

    self.guessFormat = function() {
      console.log(ko.mapping.toJSON(self.fileFormat));
      viewModel.isLoading(true);
      $.post("${ url('indexer:guess_format') }", {
        "fileFormat": ko.mapping.toJSON(self.fileFormat)
      }, function(resp) {

        self.fileFormat().format(ko.mapping.fromJS(resp));

        self.fileFormat().show(true);

        viewModel.isLoading(false);
      }).fail(function (xhr, textStatus, errorThrown) {
        $(document).trigger("error", xhr.responseText);

        viewModel.isLoading(false);
      });
    }

    self.guessFieldTypes = function(){
      console.log("guess field types...");
      if(guessFieldTypesXhr) guessFieldTypesXhr.abort();
      guessFieldTypesXhr = $.post("${ url('indexer:guess_field_types') }",{
        "fileFormat": ko.mapping.toJSON(self.fileFormat)
      }, function(resp){
        resp.columns.forEach(function(entry, i, arr){
          arr[i] = ko.mapping.fromJS(entry);
        });
        self.fileFormat().columns(resp.columns);

        self.sample(resp.sample);
      }).fail(function (xhr, textStatus, errorThrown) {
        $(document).trigger("error", xhr.responseText);

        viewModel.isLoading(false);
      });;
    };

    self.indexFile = function() {
      console.log(ko.mapping.toJSON(self.fileFormat));

      self.indexingStarted(true);

      console.log(self.indexingStarted());

      viewModel.isLoading(true);

      $.post("${ url('indexer:index_file') }", {
        "fileFormat": ko.mapping.toJSON(self.fileFormat)
      }, function(resp) {
        self.showCreate(true);
        self.jobId(resp.jobId);
        console.log(self.jobId());
        viewModel.isLoading(false);
      }).fail(function (xhr, textStatus, errorThrown) {
        $(document).trigger("error", xhr.responseText);
        viewModel.isLoading(false);
      });
    }
  };

  var Editor = function () {
    var self = this;

    self.createWizard = new CreateWizard(self);
    self.isLoading = ko.observable(false);

  };

  var viewModel;

  $(document).ready(function () {
    viewModel = new Editor();
    ko.applyBindings(viewModel);
  });
</script>


${ commonfooter(request, messages) | n,unicode }
