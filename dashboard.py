import gc
import helper
import constants
import pandas as pd
import gradio as gr
from haystack.pipelines import QuestionAnswerGenerationPipeline
from haystack.document_stores import ElasticsearchDocumentStore
from haystack.nodes import QuestionGenerator, FARMReader, BM25Retriever, EmbeddingRetriever

selected_rows = []

def init_pipeline():
    question_generator = QuestionGenerator(model_name_or_path='valhalla/t5-base-e2e-qg',
                                            max_length=420, split_length=75, 
                                            split_overlap=20, use_gpu=True)
    #qa_model = 'deepset/deberta-v3-large-squad2'
    qa_model = 'deepset/roberta-base-squad2'
    reader = FARMReader(model_name_or_path=qa_model,
                        top_k=1, use_gpu=True)
    pipeline = QuestionAnswerGenerationPipeline(question_generator, reader)
    return pipeline

def upload_csv(topic, file, labels, data_source):
    """
    Load CSV to Elasticsearch document store and apply zero shot classification.
    """
    print('Uploading CSV')
    gr.Info(f'Uploading file to Elasticsearch. Please wait.')
    if data_source == 'OpenStax.org':
        docs = helper.openstax_to_doc(path=file.name)
    else:
        raise NotImplementedError
    
    doc_store = helper.add_to_docstore(docs, index=topic, delete_docs=True)
    if labels != '':
        labels = labels.split(',')
        labels = [label.strip() for label in labels]
        doc_store = helper.classify_docs(labels=labels, doc_store=doc_store, index=topic)
        return [gr.update(value=f'CSV added to Elasticsearch under {topic}.\nLabels added.', visible=True),
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=True)]

    return [gr.update(value=f'CSV added to Elasticsearch under {topic}.', visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True)]


def generate_qa_pairs(topic, retrieval_query, emb_retrieval_query):
    """
    Generate QA pair on the uploaded CSV.  
    If query passed, filter documents based on BM25 retrieval.
    Saves generated QA pairs to CSV.
    """
    print('Generating QA Pairs')
    gr.Info('Generating QA Pairs. Please wait.')
    retrieval_flag = False
    emb_retrieval_flag = False

    if retrieval_query == '' and emb_retrieval_query == '':
        retrieval_flag = False
        doc_store = ElasticsearchDocumentStore(index=topic)
        docs = doc_store.get_all_documents()

    elif retrieval_query != '' and emb_retrieval_query == '':
        retrieval_flag = True
        doc_store = ElasticsearchDocumentStore(index=topic)
        retriever = BM25Retriever(document_store=doc_store)
        docs = retriever.retrieve(query=retrieval_query)
    
    elif emb_retrieval_query != '' and retrieval_query == '':
        emb_retrieval_flag = True
        doc_store = ElasticsearchDocumentStore(index=topic, similarity='dot_product', embedding_dim=768)
        retriever = EmbeddingRetriever(document_store=doc_store, embedding_model='sentence-transformers/all-mpnet-base-v2',
                                       model_format='sentence_transformers')
        doc_store.update_embeddings(retriever=retriever)
        docs = retriever.retrieve(query=emb_retrieval_query)
    
    global df_gen_qa
    pipeline = init_pipeline()
    df_gen_qa = helper.run_pipeline(pipeline, docs)
    del pipeline
    gc.collect()
    path = f'data/{topic}_generated_QA.csv'
    df_gen_qa.to_csv(path, index=False)

    # Convert to FXN
    if retrieval_flag:
        qa_output_str = f'BM25 - {len(df_gen_qa)} QA pairs were generated using documents filtered on "{retrieval_query}". Download the file below.'
    elif emb_retrieval_flag:
        qa_output_str = f'Embedding retrieval - {len(df_gen_qa)} QA pairs were generated using documents filtered on "{emb_retrieval_query}". Download the file below.'
    else:
        qa_output_str = f'{len(df_gen_qa)} QA pairs were generated. Download the file below.'

    #del doc_store
    return [gr.update(value=qa_output_str, visible=True),
            gr.update(value=path, visible=True),
            gr.update(value=df_gen_qa, visible=True),
            gr.update(visible=True), 
            gr.update(visible=True), 
            gr.update(visible=True),
            gr.update(visible=True)]

def generate_distractors(file, topic, distractor_count):
    gc.collect()
    df = pd.read_csv(file.name)
    print('Generating distractors')
    distractor_count = int(distractor_count)
    #global reader, question_generator, pipeline
    #del reader, question_generator, pipeline
    
    if any(df.columns != constants.DIST_COLS):
        gr.Error('Uploaded CSV has incorrect format.')
    else:
        #global reader, pipeline, qa_model, question_generator
        #del reader
        #del pipeline
        #del qa_model
        #del question_generator
        gc.collect()
        # Rare usage, importing here to prevent memory overload by Word2Vec and LLMs
        import distractor_generation
        gr.Info('Generating distractors')
        df['distractors'] = df['generated_answer'].apply(lambda x: 
                                                        distractor_generation.generate_disctractors(answer=x, 
                                                                                                    distractor_count=distractor_count))
        # Convert string numeric answer with int numeric answer
        df['generated_answer'] = df['generated_answer'].apply(lambda x: distractor_generation.convert_numeric_answer(answer=x))
        # Code taken from https://stackoverflow.com/questions/43752845/list-of-values-to-columns-in-pandas-dataframe
        df_distractor = pd.DataFrame(df['distractors'].values.tolist()).add_prefix(constants.COL_PREFIX)
        df_distractor = df_distractor.join(df[constants.DIST_COLS])
        # Reorder columns
        df_distractor = df_distractor[constants.DIST_COLS+[constants.COL_PREFIX+str(_) for _ in range(distractor_count)]]
        
        path = f'data/{topic}_gen_QA_distractor.csv'
        df_distractor.to_csv(path, index=False)
        
        return gr.update(value=path, visible=True)


def change_label(topic):
    # Change label based on input from user.
    return gr.update(label=f'Add {topic} CSV')


def add_row(event: gr.SelectData):
    """
    Save selected rows (from QA pair df) to CSV.
    This helps in quicker filtering of data for researchers.
    """
    print(f'{event.index[0]} row added')
    selected_rows.append(event.index[0])
    #selected_rows = list(set(selected_rows))
    df_select = df_gen_qa.iloc[selected_rows, :]
    path = f'data/selected_data.csv'
    df_select.to_csv(path, index=False)
    return gr.update(value=path)


theme = gr.themes.Soft()
with gr.Blocks(css=constants.css, title=constants.tab_title, theme=theme) as dashboard:
    gr.HTML(constants.page_title)
    with gr.Row():
        topic = gr.Textbox(label='Topic', 
                           placeholder='openstax_biology, ck12_economics...')
        data_source = gr.Dropdown(['OpenStax.org', 'CK12.org', 'Brightstorm'],
                                  label='Data Source')
        labels = gr.Textbox(label='Zero Shot Labels', 
                            placeholder= 'Add labels science, economics, technology...(use , to split)')
    
    file = gr.File(file_types=['csv'], label='Add CSV')
    topic.change(fn=change_label, inputs=topic, outputs=file)    
    upload_btn = gr.Button('Upload')
    data_output_box = gr.Textbox(label='Data Upload Status', visible=False)
    
    with gr.Row():
        retrieval_query = gr.Textbox(label='Retrieval Query - BM25', placeholder='Enter query', 
                                    visible=False)
        emb_retrieveal_query = gr.Textbox(label='Retrieval Query - Embedding based', placeholder='Enter query',
                                        visible=False)
    generate_qa_btn = gr.Button(f'Generate Question Answer Pairs', visible=False)

    upload_btn.click(fn=upload_csv,
                    inputs=[topic, file, labels, data_source], 
                    outputs=[data_output_box, generate_qa_btn, retrieval_query, emb_retrieveal_query])

    qa_output_box = gr.Textbox(label='Generated QA Pairs Status', visible=False)
    generated_file = gr.File(label='Generated CSV', visible=False)
    df_output = gr.Dataframe(label='Generated QA Pairs', visible=False, wrap=True, 
                             show_label=True, interactive=False)
    selected_rows_file = gr.File(label='Download selected rows', visible=False)
    
    distractor_file = gr.File(label='Add CSV to generate distractors', visible=False, file_types=['csv'])
    distractor_count = gr.Number(label='Distractor Counts', value=5 , visible=False)

    generate_distr_btn = gr.Button(value='Upload',label='Upload', visible=False)
    generated_distr_file = gr.File(label='Generated QA-Distractors CSV', visible=False)

    generate_qa_btn.click(fn=generate_qa_pairs, 
                          inputs=[topic, retrieval_query, emb_retrieveal_query], 
                          outputs=[qa_output_box, generated_file, df_output, selected_rows_file, 
                                   distractor_file, generate_distr_btn, distractor_count])
    df_output.select(fn=add_row, inputs=None, outputs=selected_rows_file)

    generate_distr_btn.click(fn=generate_distractors,
                            inputs=[distractor_file, topic, distractor_count],
                            outputs=generated_distr_file)

    
dashboard.queue().launch(server_port=8080, share=False)

# TODO - 
# change output in gen_qa_pairs on status update
# display generated qa pair df -> make it run for tqdm(run doc)
#
# 1. data loader for all formats.
# 2. TDQMs
# 3. Option to choose different models in dashboard
# 4. Set visibility to False for output_box, later True.
# 5. Add data filtering (via class labels)
# 6. Give option to select QA model
# 7. Give option to select number of distractors
# 8. Readme word2vec downloading, memory requirements (13 GB)
# 9. DONE: Remove stopwords from distractors (the cell, an acid)
# 10. DONE: Numbers for Distractor Generation