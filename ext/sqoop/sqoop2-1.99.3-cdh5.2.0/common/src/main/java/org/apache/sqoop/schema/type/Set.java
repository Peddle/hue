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
package org.apache.sqoop.schema.type;

/**
 * Multiple values of the same type.
 *
 * JDBC Types: set
 */
public class Set extends AbstractComplexType {

  public Set(Column key) {
    super(key);
  }

  public Set(String name, Column key) {
    super(name, key);
  }

  public Set(String name, Boolean nullable, Column key) {
    super(name, nullable, key);
  }

  @Override
  public Type getType() {
    return Type.SET;
  }

  @Override
  public String toString() {
    return new StringBuilder("Set{")
      .append(super.toString())
      .append("}")
      .toString();
  }
}
