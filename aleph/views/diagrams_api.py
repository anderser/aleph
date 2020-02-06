import logging
from banal import first
from flask import Blueprint, request

from aleph.core import db
from aleph.model import Diagram, Entity
from aleph.logic.entities import update_entity
from aleph.logic.diagrams import replace_layout_ids, replace_entity_ids
from aleph.search import QueryParser, DatabaseQueryResult
from aleph.views.serializers import DiagramSerializer
from aleph.views.util import get_db_collection, parse_request
from aleph.views.util import obj_or_404, require


blueprint = Blueprint('diagrams_api', __name__)
log = logging.getLogger(__name__)


@blueprint.route('/api/2/diagrams', methods=['GET'])
def index():
    """Returns a list of diagrams for the role
    ---
    get:
      summary: List diagrams
      parameters:
      - description: The collection id.
        in: query
        name: 'filter:collection_id'
        required: true
        schema:
          minimum: 1
          type: integer
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                allOf:
                - $ref: '#/components/schemas/QueryResponse'
                properties:
                  results:
                    type: array
                    items:
                      $ref: '#/components/schemas/Diagram'
          description: OK
      tags:
        - Diagram
    """
    require(request.authz.logged_in)
    parser = QueryParser(request.args, request.authz)
    collection_id = first(parser.filters.get('collection_id'))
    q = Diagram.by_role_id(request.authz.id)
    if collection_id:
        get_db_collection(collection_id)
        q = q.filter(Diagram.collection_id == collection_id)
    result = DatabaseQueryResult(request, q)
    return DiagramSerializer.jsonify_result(result)


@blueprint.route('/api/2/diagrams', methods=['POST', 'PUT'])
def create():
    """Create a diagram.
    ---
    post:
      summary: Create a diagram
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DiagramCreate'
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'
          description: OK
      tags:
      - Diagram
    """
    data = parse_request('DiagramCreate')
    collection_id = data.pop('collection_id')
    collection = get_db_collection(collection_id, request.authz.WRITE)
    entities = data.pop('entities', [])
    old_to_new_id_map = {}
    entity_ids = []
    for ent_data in entities:
        old_id = ent_data.pop('id')
        # check that every entity id is namespaced properly
        entity_id = old_id
        if not collection.ns.verify(entity_id):
            entity_id = collection.ns.sign(entity_id)
            old_to_new_id_map[old_id] = entity_id
        entity_ids.append(entity_id)
        ent_data = replace_entity_ids(ent_data, old_to_new_id_map)
        # If an entity exists already, undelete and update it
        entity = Entity.by_id(entity_id, deleted=True)
        if entity is not None:
            if entity.deleted_at is not None:
                entity.undelete()
            entity.update(ent_data)
        # else create it with the supplied id
        else:
            entity = Entity.create(ent_data, collection, entity_id=entity_id)
            collection.touch()
        update_entity(entity, sync=True)
        db.session.commit()
    data['entities'] = entity_ids
    layout = data.get('layout', {})
    if layout:
        data['layout'] = replace_layout_ids(data['layout'], old_to_new_id_map)
    diagram = Diagram.create(data, collection, request.authz.id)
    db.session.commit()
    return DiagramSerializer.jsonify(diagram)


@blueprint.route('/api/2/diagrams/<int:diagram_id>', methods=['GET'])
def view(diagram_id):
    """Return the diagram with id `diagram_id`.
    ---
    get:
      summary: Fetch a diagram
      parameters:
      - description: The diagram id.
        in: path
        name: diagram_id
        required: true
        schema:
          minimum: 1
          type: integer
        example: 2
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'
          description: OK
      tags:
      - Diagram
    """
    diagram = obj_or_404(Diagram.by_id(diagram_id))
    get_db_collection(diagram.collection_id, request.authz.READ)
    return DiagramSerializer.jsonify(diagram)


@blueprint.route('/api/2/diagrams/<int:diagram_id>', methods=['POST', 'PUT'])
def update(diagram_id):
    """Update the diagram with id `diagram_id`.
    ---
    post:
      summary: Update a diagram
      parameters:
      - description: The diagram id.
        in: path
        name: diagram_id
        required: true
        schema:
          minimum: 1
          type: integer
        example: 2
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DiagramUpdate'
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Diagram'
          description: OK
      tags:
      - Diagram
    """
    diagram = obj_or_404(Diagram.by_id(diagram_id))
    get_db_collection(diagram.collection_id, request.authz.WRITE)
    data = parse_request('DiagramUpdate')
    diagram.update(data=data)
    return DiagramSerializer.jsonify(diagram)


@blueprint.route('/api/2/diagrams/<int:diagram_id>', methods=['DELETE'])
def delete(diagram_id):
    """Delete a diagram.
    ---
    delete:
      summary: Delete a diagram
      parameters:
      - description: The diagram id.
        in: path
        name: diagram_id
        required: true
        schema:
          minimum: 1
          type: integer
        example: 2
      responses:
        '204':
          description: No Content
      tags:
      - Diagram
    """
    diagram = obj_or_404(Diagram.by_id(diagram_id))
    get_db_collection(diagram.collection_id, request.authz.WRITE)
    diagram.delete()
    return ('', 204)