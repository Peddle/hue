/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.sqoop.json;

import org.apache.sqoop.json.util.SchemaSerialization;
import org.apache.sqoop.schema.Schema;
import org.json.simple.JSONObject;

/**
 *
 */
public class SchemaBean implements JsonBean {

  private Schema schema;

  // For "extract"
  public SchemaBean(Schema schema) {
    this.schema = schema;
  }

  // For "restore"
  public SchemaBean() {
  }

  public Schema getSchema() {
    return schema;
  }

  @Override
  public JSONObject extract(boolean skipSensitive) {
    return SchemaSerialization.extractSchema(schema);
  }

  @Override
  public void restore(JSONObject jsonObject) {
    schema = SchemaSerialization.restoreSchemna(jsonObject);
  }

}
