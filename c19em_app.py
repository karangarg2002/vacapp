"""Streamlit app for FOIA Explorer COVID-19 Emails"""
import streamlit as st
import pandas as pd
import altair as alt
import psycopg2
import datetime
from st_aggrid import AgGrid
from st_aggrid.grid_options_builder import GridOptionsBuilder


st.set_page_config(page_title="FOIA Explorer: COVID-19 Emails", layout="wide")
st.title("FOIA Explorer: COVID-19 Emails")
"""
The COVID-19 releated emails of Dr. Anthony Fauci, director of the National
Institute of Allergy and Infectious Diseases.
- Source: MuckRock/DocumentCloud | Contributor: Jason Leopold
- https://www.documentcloud.org/documents/20793561-leopold-nih-foia-anthony-fauci-emails
"""


# initialize database connection - uses st.cache to only run once
@st.cache(allow_output_mutation=True,
          hash_funcs={"_thread.RLock": lambda _: None})
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])


# perform query - ses st.cache to only rerun once
@st.cache
def run_query(query):
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


@st.cache
def get_entity_list(qual):
    entsfw = 'SELECT entity from covid19.entities where entity_id <= 515 and \
    enttype '
    entorder = 'order by entity'
    lov = []
    rows = run_query(entsfw + qual + entorder)
    for r in rows:
        lov.append(r[0])
    return(lov)


@st.cache
def get_topic_list():
    tq = """select distinct top_topic
               from covid19.fauci_emails
               where top_topic is not null"""
    lov = []
    rows = run_query(tq)
    for r in rows:
        lov.append(r[0])
    return(lov)


conn = init_connection()

# build dropdown lists for entity search
person_list = get_entity_list("= 'PERSON' ")
org_list = get_entity_list("= 'ORG' ")
loc_list = get_entity_list("in ('GPE', 'LOC', 'NORP', 'FAC') ")
topic_list = get_topic_list()

"""## Daily Email Volume, January - May 2020"""

emcnts = """
select date(sent) date, count(*) emails
    from covid19.emails
    where file_id = 1000 and sent >= '2020-01-01'
    group by date
    order by date;
"""

cntsdf = pd.read_sql_query(emcnts, conn)
c = alt.Chart(cntsdf).mark_bar().encode(
    x=alt.X('date:T', scale=alt.Scale(domain=('2020-01-23', '2020-05-06'))),
    y=alt.Y('emails:Q', scale=alt.Scale(domain=(0, 60)))
    )
st.altair_chart(c, use_container_width=True)

"""## Search Emails """
with st.form(key='query_params'):
    cols = st.columns(2)
    begin_date = cols[0].date_input('Start Date', datetime.date(2020, 1, 23))
    end_date = cols[1].date_input('End Date', datetime.date(2020, 5, 6))
    persons = st.multiselect('Person(s):', person_list)
    orgs = st.multiselect('Organization(s):', org_list)
    locations = st.multiselect('Location(s):', loc_list)
    topics = st.multiselect('Topic(s):', topic_list)
    ftq_text = st.text_input('Full Text Search:', '',
                             help='Perform full text search. Use double quotes \
                             for phrases, OR for logical or, and - for \
                             logical not.')
    query = st.form_submit_button(label='Execute Search')
    where_ent = where_ft = ''


""" ## Search Results """
entities = persons + orgs + locations
selfrom = """
select email_id, pg_number, sent, subject, from_email "from", to_emails "to",
       top_topic, entities
    from covid19.fauci_emails
"""
where = f"where sent between '{begin_date}' and '{end_date}'"
qry_explain = where[6:].replace("'", "")
where_ent = where_ft = where_top = ''
if entities:
    # build entity in list
    entincl = "'{"
    for e in entities:
        entincl += f'"{e}", '
    entincl = entincl[:-2] + "}'"
    where_ent = f" and entities && {entincl}::text[]"
    tq = ''
    if len(entities) > 1:
        tq = 'at least one of'
    qry_explain += f" and email references {tq} {entincl[2:-2]}"
if topics:
    topincl = "("
    for t in topics:
        topincl += f"'{t}', "
    topincl = topincl[:-2] + ')'
    where_top = f" and top_topic in {topincl}"
    qry_explain += f" and topic is {topincl[1:-1]}"
if ftq_text:
    if ftq_text[0] == "'":         # replace single quote with double
        ftq_text = '"' + ftq_text[1:-1:] + '"'
    where_ft = f" and to_tsvector('english', body) @@ websearch_to_tsquery\
('english', '{ftq_text}')"
    qry_explain += f' and text body contains "{ftq_text}"'
# execute query
emqry = selfrom + where + where_ent + where_top + where_ft + ' order by sent'
emdf = pd.read_sql_query(emqry, conn)
emcnt = len(emdf.index)
st.markdown(f"{emcnt} emails {qry_explain}")
# download results as CSV
csv = emdf.to_csv().encode('utf-8')
st.download_button(label="CSV download", data=csv,
                   file_name='foia-covid19.csv', mime='text/csv')
# generate AgGrid
gb = GridOptionsBuilder.from_dataframe(emdf)
gb.configure_default_column(value=True, editable=False)
gb.configure_grid_options(domLayout='normal')
gb.configure_selection(selection_mode='single', groupSelectsChildren=False)
gb.configure_column('email_id', hide=True)
gb.configure_column('pg_number', hide=True)
gb.configure_column('top_topic', hide=True)
gb.configure_column('entities', hide=True)
gb.configure_column('sent', maxWidth=150)
gb.configure_column('subject', maxWidth=600)
gb.configure_column('from', maxWidth=225)
gb.configure_column('to', maxWidth=425)

# gb.configure_pagination(paginationAutoPageSize=True) - original
# gb.configure_auto_height(autoHeight=False)           - new, and next line
# gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=50)

gridOptions = gb.build()

grid_response = AgGrid(emdf,
                       gridOptions=gridOptions,
                       return_mode_values='AS_INPUT',
                       update_mode='SELECTION_CHANGED',
                       allow_unsafe_jscode=False,
                       enable_enterprise_modules=False)
selected = grid_response['selected_rows']

# define DocumentCloud references
dc_base = 'https://www.documentcloud.org/documents/'
dc_aws = 'https://s3.documentcloud.org/documents/'
dc_id = '20793561'
dc_slug = 'leopold-nih-foia-anthony-fauci-emails'
dc_gif_sz = 'large'
dc_doc_url = dc_base + dc_id + '-' + dc_slug
dc_pg_gif = dc_base + dc_id + '/pages/' + dc_slug + '-p{pg}-' + dc_gif_sz + \
            '.gif'
dc_aws_pdf = dc_aws + dc_id + '/' + dc_slug + '.pdf'

if selected:
    """## Email Details"""
    el_disp = selected[0]["entities"][1:-1].replace("'", "")
    st.markdown(f'**Entities**: `{el_disp}`')
    st.markdown(f'**Topic Words:** `{selected[0]["top_topic"]}`')
    pg = int(selected[0]["pg_number"])
    st.markdown('**Email Preview:** ')
    st.markdown('<iframe src=' + dc_pg_gif.format(pg=pg) +
                ' width="100%" height="1300">', unsafe_allow_html=True)
    st.markdown(f'[**View Full Email on DocumentCloud**]({dc_aws_pdf}#page=\
{pg})')

else:
    st.write('Select row to view additional email details')
"""
## About
The FOIA Explorer and associated tools were created by Columbia
Univesity's [History Lab](http://history-lab.org) under a grant from the Mellon
Foundation's [Email Archives: Building Capacity and Community]
(https://emailarchivesgrant.library.illinois.edu/blog/) program.
"""
